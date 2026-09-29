import uuid

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lightchat_profile")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    display_name = models.CharField(max_length=80)
    membership_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name


class AccountBalance(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lightchat_balance")
    available_credits = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class UserSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lightchat_settings")
    global_system_prompt = models.TextField(blank=True, validators=[MaxLengthValidator(4000)])
    updated_at = models.DateTimeField(auto_now=True)


class MemoryItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memory_items")
    content = models.CharField(max_length=500)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=120, default="New conversation")
    system_instructions = models.TextField(blank=True, validators=[MaxLengthValidator(4000)])
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    class ExecutionMode(models.TextChoices):
        MOCK = "mock", "Mock"
        LITECHAT = "litechat", "LiteChat proxy"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    provider = models.CharField(max_length=24, blank=True)
    model_key = models.CharField(max_length=64, blank=True)
    execution_mode = models.CharField(max_length=16, choices=ExecutionMode.choices, default=ExecutionMode.MOCK)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


def attachment_upload_to(instance, filename):
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"uploads/{instance.message.session.owner_id}/{instance.message.session_id}/{uuid.uuid4().hex}.{suffix}"


class Attachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_upload_to)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=80)
    size = models.PositiveIntegerField()
    is_image = models.BooleanField(default=False)
    extracted_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GenerationRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="generation_requests")
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="generation_requests")
    user_message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="generation_requests")
    assistant_message = models.OneToOneField(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="generation")
    idempotency_key = models.UUIDField()
    provider = models.CharField(max_length=24)
    model_key = models.CharField(max_length=64)
    execution_mode = models.CharField(max_length=16, choices=Message.ExecutionMode.choices, default=Message.ExecutionMode.MOCK)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    cost_credits = models.PositiveIntegerField()
    error_code = models.CharField(max_length=48, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="unique_generation_key_per_user"),
        ]
        ordering = ["-created_at"]


class CreditLedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        INITIAL_GRANT = "initial_test_grant", "Initial test credit grant"
        GENERATION_CHARGE = "generation_charge", "Generation charge"
        FAILED_RELEASE = "failed_request_release", "Failed request release"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credit_entries")
    generation = models.ForeignKey(GenerationRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_entries")
    entry_type = models.CharField(max_length=32, choices=EntryType.choices)
    amount = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    description = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Feedback(models.Model):
    class Rating(models.TextChoices):
        UP = "up", "Helpful"
        DOWN = "down", "Not helpful"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback")
    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="feedback")
    rating = models.CharField(max_length=8, choices=Rating.choices)
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
