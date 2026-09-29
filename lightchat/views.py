import base64
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .catalog import THINKING_EFFORTS, get_model_option, get_model_options
from .forms import (
    ChatInstructionsForm,
    ChatRenameForm,
    FeedbackForm,
    GlobalPromptForm,
    MemoryItemForm,
    ProfileForm,
    RegistrationForm,
)
from .models import (
    AccountBalance,
    Attachment,
    ChatSession,
    CreditLedgerEntry,
    Feedback,
    GenerationRequest,
    MemoryItem,
    Message,
    UserSettings,
)
from .providers import ProviderError, get_provider
from .services import (
    UploadValidationError,
    build_context,
    prepare_attachments,
    provision_account,
    release_failed_generation,
    save_attachments,
)

User = get_user_model()


def signup(request):
    if request.user.is_authenticated:
        return redirect("chat-home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            provision_account(user, form.cleaned_data["display_name"].strip())
        login(request, user)
        return redirect("chat-home")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def chat_home(request):
    chats = request.user.chat_sessions.filter(archived=False)
    current = chats.first()
    if current:
        return redirect("chat-detail", chat_id=current.id)
    return render(
        request,
        "lightchat/chat_empty.html",
        {"chats": chats, "balance": request.user.lightchat_balance.available_credits},
    )


@login_required
@require_POST
def create_chat(request):
    title = request.POST.get("title", "").strip()[:120] or "New conversation"
    chat = ChatSession.objects.create(owner=request.user, title=title)
    return redirect("chat-detail", chat_id=chat.id)


@login_required
def chat_detail(request, chat_id):
    chat = get_object_or_404(ChatSession, id=chat_id, owner=request.user, archived=False)
    chats = request.user.chat_sessions.filter(archived=False)
    return render(
        request,
        "lightchat/chat.html",
        {
            "chat": chat,
            "chats": chats,
            "messages_list": chat.messages.prefetch_related("attachments", "feedback").all(),
            "model_options": get_model_options(settings.LIGHTCHAT_PROVIDER_MODE),
            "provider_mode": settings.LIGHTCHAT_PROVIDER_MODE,
            "balance": request.user.lightchat_balance.available_credits,
            "instructions_form": ChatInstructionsForm(instance=chat),
        },
    )


def generation_json(generation):
    message = generation.assistant_message
    return {
        "ok": True,
        "message": {
            "id": str(message.id),
            "role": message.role,
            "content": message.content,
            "provider": message.provider,
            "model_key": message.model_key,
            "execution_mode": message.execution_mode,
            "attachments": [
                {"name": item.original_name, "url": reverse("download-attachment", args=[item.id])}
                for item in message.attachments.all()
            ],
            "feedback_url": reverse("submit-feedback", args=[message.id]),
        },
        "balance": generation.user.lightchat_balance.available_credits,
        "cost": generation.cost_credits,
        "replayed": True,
    }


def complete_generation(generation, option, *, replayed, thinking_effort="medium"):
    user = generation.user
    chat = generation.session
    user_message = generation.user_message
    try:
        prepared_attachments = []
        for attachment in user_message.attachments.all():
            item = {
                "name": attachment.original_name,
                "is_image": attachment.is_image,
                "content_type": attachment.content_type,
                "extracted_text": attachment.extracted_text,
            }
            if generation.execution_mode == Message.ExecutionMode.LITECHAT and attachment.is_image:
                try:
                    with attachment.file.open("rb") as image_file:
                        image_bytes = image_file.read(settings.LIGHTCHAT_MAX_UPLOAD_BYTES + 1)
                except OSError:
                    raise ProviderError("An attached image could not be read.", status=400, code="image_read_error") from None
                if len(image_bytes) > settings.LIGHTCHAT_MAX_UPLOAD_BYTES:
                    raise ProviderError("An attached image exceeds the configured upload limit.", status=400, code="image_too_large")
                item["image_data"] = base64.b64encode(image_bytes).decode("ascii")
            prepared_attachments.append(item)

        context = build_context(user, chat, user_message, prepared_attachments)
        provider = get_provider(
            generation.execution_mode,
            proxy_url=settings.LITECHAT_PROXY_URL,
            api_keys=settings.LITECHAT_API_KEYS,
        )
        response_text = provider.generate(
            option=option,
            prompt=user_message.content,
            context=context,
            attachments=prepared_attachments,
            thinking_effort=thinking_effort,
        )
    except ProviderError as exc:
        released = release_failed_generation(
            generation,
            user,
            error_code=exc.code,
            description="Test credits released after a failed provider request",
        )
        generation.refresh_from_db()
        if not released and generation.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(generation))
        return JsonResponse(
            {"ok": False, "error": f"{exc}. Your test credits were released."},
            status=exc.status,
        )
    except Exception:
        released = release_failed_generation(
            generation,
            user,
            error_code="provider_internal_error",
            description="Test credits released after an internal provider error",
        )
        generation.refresh_from_db()
        if not released and generation.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(generation))
        return JsonResponse(
            {"ok": False, "error": "The provider request failed. Your test credits were released."},
            status=502,
        )

    with transaction.atomic():
        generation = GenerationRequest.objects.select_for_update().select_related("user", "session").get(pk=generation.pk)
        if generation.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(generation))
        if generation.status == GenerationRequest.Status.FAILED:
            return JsonResponse({"ok": False, "error": "This request already failed."}, status=409)

        assistant_message = Message.objects.create(
            session=chat,
            role=Message.Role.ASSISTANT,
            content=response_text,
            provider=option["provider"],
            model_key=option["key"],
            execution_mode=generation.execution_mode,
        )
        generation.assistant_message = assistant_message
        generation.status = GenerationRequest.Status.SUCCEEDED
        generation.completed_at = timezone.now()
        generation.save(update_fields=["assistant_message", "status", "completed_at"])
        if chat.title == "New conversation":
            prompt = user_message.content
            chat.title = prompt[:54] + ("..." if len(prompt) > 54 else "")
        chat.save(update_fields=["title", "updated_at"])

    return JsonResponse(generation_json(generation) | {"replayed": replayed})


@login_required
@require_POST
def generate(request, chat_id):
    chat = get_object_or_404(ChatSession, id=chat_id, owner=request.user, archived=False)
    prompt = request.POST.get("prompt", "").strip()
    if not prompt:
        return JsonResponse({"ok": False, "error": "Enter a prompt first."}, status=400)
    if len(prompt) > 12000:
        return JsonResponse({"ok": False, "error": "Prompts can contain up to 12,000 characters."}, status=400)

    option = get_model_option(request.POST.get("model_key", ""))
    if option is None:
        return JsonResponse({"ok": False, "error": "Choose a supported model."}, status=400)
    thinking_effort = request.POST.get("thinking_effort", "medium").strip().lower()
    if thinking_effort not in THINKING_EFFORTS:
        return JsonResponse({"ok": False, "error": "Choose a valid thinking effort."}, status=400)

    provider_mode = settings.LIGHTCHAT_PROVIDER_MODE
    if provider_mode not in {Message.ExecutionMode.MOCK, Message.ExecutionMode.LITECHAT}:
        return JsonResponse(
            {"ok": False, "error": "The configured provider mode is not supported."},
            status=503,
        )

    try:
        request_id = uuid.UUID(request.POST.get("request_id", ""))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"ok": False, "error": "Refresh the page and try again."}, status=400)

    prior = GenerationRequest.objects.filter(user=request.user, idempotency_key=request_id).first()
    if prior:
        if prior.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(prior))
        if prior.status == GenerationRequest.Status.PENDING:
            if prior.execution_mode == Message.ExecutionMode.MOCK:
                option = get_model_option(prior.model_key)
                if option:
                    return complete_generation(
                        prior,
                        option,
                        replayed=True,
                        thinking_effort=thinking_effort,
                    )
            return JsonResponse(
                {"ok": False, "error": "A previous provider request may still be running; it was not retried."},
                status=409,
            )
        return JsonResponse({"ok": False, "error": "This request was already submitted."}, status=409)

    if provider_mode == Message.ExecutionMode.LITECHAT:
        if not option.get("upstream_model_id"):
            return JsonResponse({"ok": False, "error": "This model is available only in mock mode."}, status=400)
        if not settings.LITECHAT_API_KEYS.get(option["provider"]):
            return JsonResponse(
                {"ok": False, "error": "The server is missing a credential for this provider."},
                status=503,
            )

    try:
        prepared_attachments = prepare_attachments(request.FILES.getlist("files"))
    except UploadValidationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    if any(item["is_image"] for item in prepared_attachments) and not option["supports_images"]:
        return JsonResponse(
            {"ok": False, "error": "This selected model does not support images. Choose an image-capable model."},
            status=400,
        )

    cost = int(option["request_cost_credits"])
    try:
        with transaction.atomic():
            balance_changed = AccountBalance.objects.filter(
                user=request.user,
                available_credits__gte=cost,
            ).update(available_credits=F("available_credits") - cost)
            if not balance_changed:
                available = request.user.lightchat_balance.available_credits
                return JsonResponse(
                    {
                        "ok": False,
                        "error": f"Not enough test credits. This model needs {cost}; your balance is {available}.",
                        "balance": available,
                        "required": cost,
                    },
                    status=402,
                )

            user_message = Message.objects.create(session=chat, role=Message.Role.USER, content=prompt)
            save_attachments(user_message, prepared_attachments)
            generation = GenerationRequest.objects.create(
                user=request.user,
                session=chat,
                user_message=user_message,
                idempotency_key=request_id,
                provider=option["provider"],
                model_key=option["key"],
                execution_mode=provider_mode,
                cost_credits=cost,
            )
            balance = AccountBalance.objects.get(user=request.user)
            CreditLedgerEntry.objects.create(
                user=request.user,
                generation=generation,
                entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE,
                amount=-cost,
                balance_after=balance.available_credits,
                description=f"{option['provider_label']} {provider_mode} generation",
            )
    except IntegrityError:
        prior = GenerationRequest.objects.filter(user=request.user, idempotency_key=request_id).first()
        if prior and prior.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(prior))
        if prior and prior.status == GenerationRequest.Status.PENDING:
            if prior.execution_mode == Message.ExecutionMode.MOCK:
                option = get_model_option(prior.model_key)
                if option:
                    return complete_generation(
                        prior,
                        option,
                        replayed=True,
                        thinking_effort=thinking_effort,
                    )
            return JsonResponse(
                {"ok": False, "error": "A previous provider request may still be running; it was not retried."},
                status=409,
            )
        return JsonResponse({"ok": False, "error": "This request was already submitted."}, status=409)
    return complete_generation(
        generation,
        option,
        replayed=False,
        thinking_effort=thinking_effort,
    )


@login_required
@require_POST
def rename_chat(request, chat_id):
    chat = get_object_or_404(ChatSession, id=chat_id, owner=request.user)
    form = ChatRenameForm(request.POST, instance=chat)
    if form.is_valid():
        form.save()
        messages.success(request, "Conversation renamed.")
    else:
        messages.error(request, "Enter a valid conversation name.")
    return redirect("chat-detail", chat_id=chat.id) if not chat.archived else redirect("chat-home")


@login_required
@require_POST
def update_chat_instructions(request, chat_id):
    chat = get_object_or_404(ChatSession, id=chat_id, owner=request.user)
    form = ChatInstructionsForm(request.POST, instance=chat)
    if form.is_valid():
        form.save()
        messages.success(request, "Chat instructions saved.")
    else:
        messages.error(request, "Instructions must be 4,000 characters or less.")
    return redirect("chat-detail", chat_id=chat.id) if not chat.archived else redirect("chat-home")


@login_required
@require_POST
def archive_chat(request, chat_id):
    chat = get_object_or_404(ChatSession, id=chat_id, owner=request.user)
    chat.archived = True
    chat.save(update_fields=["archived", "updated_at"])
    messages.success(request, "Conversation archived.")
    return redirect("chat-home")


@login_required
@require_POST
def delete_chat(request, chat_id):
    chat = get_object_or_404(ChatSession, id=chat_id, owner=request.user)
    chat.delete()
    messages.success(request, "Conversation deleted.")
    return redirect("chat-home")


@login_required
def settings_view(request):
    profile_form = ProfileForm(user=request.user)
    prompt_form = GlobalPromptForm(instance=UserSettings.objects.get_or_create(user=request.user)[0])
    return render(
        request,
        "lightchat/settings.html",
        {
            "profile_form": profile_form,
            "prompt_form": prompt_form,
            "memory_form": MemoryItemForm(),
            "memories": request.user.memory_items.all(),
            "balance": request.user.lightchat_balance.available_credits,
            "ledger": request.user.credit_entries.select_related("generation").all()[:30],
        },
    )


@login_required
@require_POST
def update_profile(request):
    form = ProfileForm(request.POST, user=request.user)
    if form.is_valid():
        request.user.username = form.cleaned_data["username"].strip()
        request.user.save(update_fields=["username"])
        request.user.lightchat_profile.display_name = form.cleaned_data["display_name"].strip()
        request.user.lightchat_profile.save(update_fields=["display_name"])
        messages.success(request, "Profile updated.")
    else:
        messages.error(request, "Check the profile fields and try again.")
    return redirect("settings")


@login_required
@require_POST
def update_global_prompt(request):
    user_settings, _ = UserSettings.objects.get_or_create(user=request.user)
    form = GlobalPromptForm(request.POST, instance=user_settings)
    if form.is_valid():
        form.save()
        messages.success(request, "Global System Prompt saved.")
    else:
        messages.error(request, "The Global System Prompt must be 4,000 characters or less.")
    return redirect("settings")


@login_required
@require_POST
def save_memory(request, memory_id=None):
    instance = get_object_or_404(MemoryItem, id=memory_id, user=request.user) if memory_id else None
    form = MemoryItemForm(request.POST, instance=instance)
    if form.is_valid():
        item = form.save(commit=False)
        item.user = request.user
        item.save()
        messages.success(request, "Memory item saved.")
    else:
        messages.error(request, "Memory items must contain 1 to 500 characters.")
    return redirect("settings")


@login_required
@require_POST
def toggle_memory(request, memory_id):
    item = get_object_or_404(MemoryItem, id=memory_id, user=request.user)
    item.enabled = not item.enabled
    item.save(update_fields=["enabled", "updated_at"])
    return redirect("settings")


@login_required
@require_POST
def delete_memory(request, memory_id):
    item = get_object_or_404(MemoryItem, id=memory_id, user=request.user)
    item.delete()
    messages.success(request, "Memory item deleted.")
    return redirect("settings")


@login_required
@require_POST
def submit_feedback(request, message_id):
    message = get_object_or_404(Message, id=message_id, session__owner=request.user, role=Message.Role.ASSISTANT)
    form = FeedbackForm(request.POST)
    if form.is_valid():
        Feedback.objects.update_or_create(
            message=message,
            defaults={
                "user": request.user,
                "rating": form.cleaned_data["rating"],
                "comment": form.cleaned_data["comment"].strip(),
            },
        )
        messages.success(request, "Feedback saved.")
    else:
        messages.error(request, "Feedback could not be saved.")
    return redirect("chat-detail", chat_id=message.session_id)


@login_required
def download_attachment(request, attachment_id):
    attachment = get_object_or_404(Attachment, id=attachment_id, message__session__owner=request.user)
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_name)
