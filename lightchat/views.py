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

from .catalog import MODEL_OPTIONS, get_model_option
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
from .providers import get_provider
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
            "model_options": MODEL_OPTIONS,
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


def complete_mock_generation(generation, option, *, replayed):
    user = generation.user
    chat = generation.session
    user_message = generation.user_message
    prepared_attachments = [
        {
            "name": attachment.original_name,
            "is_image": attachment.is_image,
            "extracted_text": attachment.extracted_text,
        }
        for attachment in user_message.attachments.all()
    ]
    context = build_context(user, chat, user_message, prepared_attachments)
    provider = get_provider("mock")
    try:
        response_text = provider.generate(
            option=option,
            prompt=user_message.content,
            context=context,
            attachments=prepared_attachments,
        )
    except Exception:
        released = release_failed_generation(generation, user)
        generation.refresh_from_db()
        if not released and generation.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(generation))
        return JsonResponse(
            {"ok": False, "error": "The demo model failed. Your test credits were released."},
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
            execution_mode=Message.ExecutionMode.MOCK,
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

    if settings.LIGHTCHAT_PROVIDER_MODE != "mock":
        return JsonResponse(
            {
                "ok": False,
                "error": "Real-provider access is unavailable until the LiteChat proxy contract is verified. Use mock mode.",
            },
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
            option = get_model_option(prior.model_key)
            if option:
                return complete_mock_generation(prior, option, replayed=True)
        return JsonResponse({"ok": False, "error": "This request was already submitted."}, status=409)

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
                execution_mode=Message.ExecutionMode.MOCK,
                cost_credits=cost,
            )
            balance = AccountBalance.objects.get(user=request.user)
            CreditLedgerEntry.objects.create(
                user=request.user,
                generation=generation,
                entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE,
                amount=-cost,
                balance_after=balance.available_credits,
                description=f"{option['provider_label']} mock generation",
            )
    except IntegrityError:
        prior = GenerationRequest.objects.filter(user=request.user, idempotency_key=request_id).first()
        if prior and prior.status == GenerationRequest.Status.SUCCEEDED:
            return JsonResponse(generation_json(prior))
        if prior and prior.status == GenerationRequest.Status.PENDING:
            option = get_model_option(prior.model_key)
            if option:
                return complete_mock_generation(prior, option, replayed=True)
        return JsonResponse({"ok": False, "error": "This request was already submitted."}, status=409)
    return complete_mock_generation(generation, option, replayed=False)


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
