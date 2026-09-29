from io import BytesIO
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import models, transaction
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from .models import (
    AccountBalance,
    Attachment,
    CreditLedgerEntry,
    GenerationRequest,
    Profile,
    UserSettings,
)

User = get_user_model()


class UploadValidationError(Exception):
    pass


def provision_account(user, display_name):
    Profile.objects.get_or_create(user=user, defaults={"display_name": display_name})
    balance, created = AccountBalance.objects.get_or_create(user=user, defaults={"available_credits": 100})
    UserSettings.objects.get_or_create(user=user)
    if created:
        CreditLedgerEntry.objects.create(
            user=user,
            entry_type=CreditLedgerEntry.EntryType.INITIAL_GRANT,
            amount=100,
            balance_after=100,
            description="Initial classroom test credits",
        )


def prepare_attachments(files):
    prepared = []
    files = list(files)
    declared_total = sum(getattr(upload, "size", 0) for upload in files)
    if declared_total > settings.LIGHTCHAT_MAX_UPLOAD_BYTES:
        raise UploadValidationError("The combined files exceed the configured upload limit.")

    for upload in files:
        declared_size = getattr(upload, "size", 0)
        if not declared_size or declared_size > settings.LIGHTCHAT_MAX_UPLOAD_BYTES:
            raise UploadValidationError("Each file must be non-empty and within the configured size limit.")
        raw = upload.read(settings.LIGHTCHAT_MAX_UPLOAD_BYTES + 1)
        upload.seek(0)
        size = len(raw)
        if not size or size > settings.LIGHTCHAT_MAX_UPLOAD_BYTES or size != declared_size:
            raise UploadValidationError("Each file must be non-empty and within the configured size limit.")

        name = PurePosixPath(upload.name.replace("\\", "/")).name[:255]
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        item = {
            "name": name,
            "bytes": raw,
            "size": size,
            "is_image": False,
            "content_type": "",
            "extracted_text": "",
        }

        if extension == "pdf" and raw.startswith(b"%PDF-"):
            item["content_type"] = "application/pdf"
            try:
                reader = PdfReader(BytesIO(raw), strict=False)
                if len(reader.pages) > 60:
                    raise UploadValidationError("PDF files can contain up to 60 pages.")
                excerpts = []
                remaining = 12000
                for page in reader.pages:
                    excerpt = (page.extract_text() or "")[:remaining]
                    excerpts.append(excerpt)
                    remaining -= len(excerpt)
                    if remaining <= 0:
                        break
                item["extracted_text"] = "\n".join(excerpts).strip()
                if not item["extracted_text"]:
                    item["extracted_text"] = "[This PDF has no extractable text.]"
            except UploadValidationError:
                raise
            except Exception as exc:
                raise UploadValidationError("This PDF could not be read.") from exc
        elif extension == "txt":
            try:
                item["extracted_text"] = raw.decode("utf-8-sig").strip()[:12000]
            except UnicodeDecodeError as exc:
                raise UploadValidationError("Text files must use UTF-8 encoding.") from exc
            if not item["extracted_text"]:
                raise UploadValidationError("Text files cannot be empty.")
            item["content_type"] = "text/plain"
        elif extension in {"png", "jpg", "jpeg"}:
            try:
                image = Image.open(BytesIO(raw))
                if image.width * image.height > 20000000:
                    raise UploadValidationError("Images must be 20 megapixels or smaller.")
                image.verify()
            except UploadValidationError:
                raise
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise UploadValidationError("The image file is not a valid PNG or JPEG.") from exc
            if extension == "png" and image.format != "PNG":
                raise UploadValidationError("The file extension does not match its image format.")
            if extension in {"jpg", "jpeg"} and image.format != "JPEG":
                raise UploadValidationError("The file extension does not match its image format.")
            item["is_image"] = True
            item["content_type"] = "image/png" if image.format == "PNG" else "image/jpeg"
            item["extracted_text"] = f"[Image attachment: {name}]"
        else:
            raise UploadValidationError("Use PDF, plain text, PNG, or JPEG files.")

        prepared.append(item)
    return prepared


def save_attachments(message, prepared):
    for item in prepared:
        attachment = Attachment(
            message=message,
            original_name=item["name"],
            content_type=item["content_type"],
            size=item["size"],
            is_image=item["is_image"],
            extracted_text=item["extracted_text"],
        )
        attachment.file.save(item["name"], ContentFile(item["bytes"]), save=True)


def build_context(user, session, current_message, current_attachments):
    parts = []
    global_prompt = UserSettings.objects.get_or_create(user=user)[0].global_system_prompt.strip()
    if global_prompt:
        parts.append(f"Global user instructions:\n{global_prompt}")
    if session.system_instructions.strip():
        parts.append(f"Chat instructions:\n{session.system_instructions.strip()}")

    memories = list(user.memory_items.filter(enabled=True).order_by("-updated_at").values_list("content", flat=True)[:12])
    if memories:
        parts.append("User memory items:\n" + "\n".join(f"- {memory}" for memory in memories))

    previous = list(
        session.messages.filter(created_at__lt=current_message.created_at)
        .order_by("-created_at")[:12]
    )
    previous.reverse()
    for message in previous:
        parts.append(f"{message.role.title()}: {message.content[:4000]}")
        for attachment in message.attachments.all():
            if not attachment.is_image and attachment.extracted_text:
                parts.append(f"File {attachment.original_name}:\n{attachment.extracted_text[:12000]}")

    remaining_file_context = 20000
    for attachment in current_attachments:
        if not attachment["is_image"]:
            excerpt = attachment["extracted_text"][:remaining_file_context]
            if excerpt:
                parts.append(f"File {attachment['name']}:\n{excerpt}")
                remaining_file_context -= len(excerpt)
        if remaining_file_context <= 0:
            break

    return "\n\n".join(parts)


def release_failed_generation(generation, user):
    with transaction.atomic():
        updated = type(generation).objects.filter(
            pk=generation.pk,
            status=GenerationRequest.Status.PENDING,
        ).update(status=GenerationRequest.Status.FAILED, error_code="mock_provider_error")
        if not updated:
            return False
        AccountBalance.objects.filter(user=user).update(
            available_credits=models.F("available_credits") + generation.cost_credits
        )
        balance = AccountBalance.objects.get(user=user)
        CreditLedgerEntry.objects.create(
            user=user,
            generation=generation,
            entry_type=CreditLedgerEntry.EntryType.FAILED_RELEASE,
            amount=generation.cost_credits,
            balance_after=balance.available_credits,
            description="Test credits released after a failed generation",
        )
        return True
