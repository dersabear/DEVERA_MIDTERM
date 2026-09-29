import os
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pypdf import PdfWriter

from .catalog import MODEL_OPTIONS
from .models import (
    AccountBalance,
    Attachment,
    ChatSession,
    CreditLedgerEntry,
    Feedback,
    GenerationRequest,
    MemoryItem,
    Message,
    Profile,
    UserSettings,
)
from .services import provision_account

User = get_user_model()


class LightChatTestCase(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media.name)
        self.media_override.enable()
        self.user = User.objects.create_user(username="sophia", password="ClassroomPass-2048")
        provision_account(self.user, "Sophia")
        self.client.force_login(self.user)
        self.chat = ChatSession.objects.create(owner=self.user)

    def tearDown(self):
        self.media_override.disable()
        self.media.cleanup()

    def generate(self, *, key="mock-openai-low", prompt="Explain this idea.", files=None, request_id=None):
        return self.client.post(
            reverse("generate", args=[self.chat.id]),
            {
                "prompt": prompt,
                "model_key": key,
                "request_id": str(request_id or uuid4()),
                "files": files or [],
            },
        )


class AccountAndProfileTests(LightChatTestCase):
    def test_registration_creates_profile_settings_and_100_credit_grant_once(self):
        self.client.logout()
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-user",
                "display_name": "New User",
                "password1": "LongClassroomPass-4048",
                "password2": "LongClassroomPass-4048",
            },
        )
        self.assertRedirects(response, reverse("chat-home"))
        user = User.objects.get(username="new-user")
        self.assertEqual(user.lightchat_balance.available_credits, 100)
        self.assertEqual(user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.INITIAL_GRANT).count(), 1)
        provision_account(user, "A different name must not reset the account")
        self.assertEqual(user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.INITIAL_GRANT).count(), 1)
        self.assertEqual(user.lightchat_profile.display_name, "New User")
        self.assertTrue(UserSettings.objects.filter(user=user).exists())

    def test_settings_show_profile_membership_and_balance(self):
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sophia")
        self.assertContains(response, str(self.user.lightchat_profile.public_id))
        self.assertContains(response, "100")

    def test_profile_update_and_global_prompt_persist(self):
        response = self.client.post(
            reverse("update-profile"), {"username": "sophia-d", "display_name": "S. Devera"}
        )
        self.assertRedirects(response, reverse("settings"))
        self.user.refresh_from_db()
        self.user.lightchat_profile.refresh_from_db()
        self.assertEqual(self.user.username, "sophia-d")
        self.assertEqual(self.user.lightchat_profile.display_name, "S. Devera")

        self.client.post(reverse("global-prompt"), {"global_system_prompt": "Use short, clear explanations."})
        self.assertEqual(self.user.lightchat_settings.global_system_prompt, "Use short, clear explanations.")

    def test_login_is_required_for_chat_and_settings(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("settings")).status_code, 302)
        self.assertEqual(self.client.get(reverse("chat-detail", args=[self.chat.id])).status_code, 302)


class GenerationAndCreditTests(LightChatTestCase):
    def test_model_costs_are_flat_configured_per_request(self):
        low = self.generate(key="mock-openai-low")
        mid = self.generate(key="mock-anthropic-mid", prompt="Compare these two ideas.")
        self.assertEqual(low.status_code, 200)
        self.assertEqual(mid.status_code, 200)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 96)
        charges = list(self.user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE))
        self.assertEqual(sorted(abs(item.amount) for item in charges), [1, 3])
        self.assertEqual(low.json()["message"]["execution_mode"], "mock")
        self.assertIn("not a response from the real provider", low.json()["message"]["content"])

    def test_all_three_provider_targets_return_mock_responses(self):
        for key, provider in [
            ("mock-openai-low", "openai"),
            ("mock-anthropic-mid", "anthropic"),
            ("mock-google-premium", "google"),
        ]:
            response = self.generate(key=key, prompt=f"Try {provider} target.")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["message"]["provider"], provider)
            self.assertEqual(response.json()["message"]["execution_mode"], "mock")

    def test_insufficient_credits_block_before_message_or_provider_call(self):
        AccountBalance.objects.filter(user=self.user).update(available_credits=0)
        with patch("lightchat.views.get_provider") as get_provider:
            response = self.generate(key="mock-google-premium")
        self.assertEqual(response.status_code, 402)
        get_provider.assert_not_called()
        self.assertEqual(self.chat.messages.count(), 0)
        self.assertEqual(GenerationRequest.objects.count(), 0)

    def test_duplicate_request_id_does_not_charge_twice(self):
        request_id = uuid4()
        first = self.generate(request_id=request_id)
        replay = self.generate(request_id=request_id)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 99)
        self.assertEqual(self.user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE).count(), 1)

    def test_retry_completes_a_pending_mock_request_without_another_charge(self):
        request_id = uuid4()
        AccountBalance.objects.filter(user=self.user).update(available_credits=99)
        user_message = Message.objects.create(session=self.chat, role=Message.Role.USER, content="A pending prompt")
        generation = GenerationRequest.objects.create(
            user=self.user,
            session=self.chat,
            user_message=user_message,
            idempotency_key=request_id,
            provider="openai",
            model_key="mock-openai-low",
            execution_mode=Message.ExecutionMode.MOCK,
            cost_credits=1,
        )
        CreditLedgerEntry.objects.create(
            user=self.user,
            generation=generation,
            entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE,
            amount=-1,
            balance_after=99,
            description="OpenAI mock generation",
        )
        response = self.generate(request_id=request_id, prompt="A pending prompt")
        generation.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(generation.status, GenerationRequest.Status.SUCCEEDED)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 99)
        self.assertEqual(self.user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE).count(), 1)

    def test_mock_provider_failure_releases_test_credits(self):
        response = self.generate(prompt="[[mock-error]] simulate provider failure")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 100)
        self.assertTrue(self.user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.FAILED_RELEASE).exists())
        entries = self.user.credit_entries.exclude(entry_type=CreditLedgerEntry.EntryType.INITIAL_GRANT)
        self.assertEqual(sum(entry.amount for entry in entries), 0)

    def test_model_catalogue_has_distinct_configured_costs_and_mock_ids_only(self):
        costs = {option["request_cost_credits"] for option in MODEL_OPTIONS}
        self.assertTrue({1, 3, 5}.issubset(costs))
        self.assertTrue(all(option["upstream_model_id"] is None for option in MODEL_OPTIONS))

    def test_model_cost_configuration_changes_future_charges_only(self):
        original = self.generate(key="mock-openai-low")
        changed = tuple(
            {**option, "request_cost_credits": 2} if option["key"] == "mock-openai-low" else option
            for option in MODEL_OPTIONS
        )
        with patch("lightchat.catalog.MODEL_OPTIONS", changed), patch("lightchat.views.MODEL_OPTIONS", changed):
            later = self.generate(key="mock-openai-low", prompt="A second configured request.")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(later.status_code, 200)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 97)
        self.assertEqual(
            sorted(GenerationRequest.objects.values_list("cost_credits", flat=True)),
            [1, 2],
        )

    @override_settings(LIGHTCHAT_PROVIDER_MODE="litechat")
    def test_real_mode_stays_blocked_without_calling_a_provider(self):
        with patch("lightchat.views.get_provider") as get_provider:
            response = self.generate()
        self.assertEqual(response.status_code, 503)
        get_provider.assert_not_called()
        self.assertEqual(GenerationRequest.objects.count(), 0)

    def test_global_prompt_and_enabled_memory_are_passed_to_mock_abstraction(self):
        self.user.lightchat_settings.global_system_prompt = "Prefer concise answers."
        self.user.lightchat_settings.save()
        self.chat.system_instructions = "Use an everyday example."
        self.chat.save()
        memory = MemoryItem.objects.create(user=self.user, content="I study biology.", enabled=True)
        with patch("lightchat.views.get_provider") as get_provider:
            provider = get_provider.return_value
            provider.generate.return_value = "A deterministic answer."
            self.generate(prompt="Explain osmosis.")
        context = provider.generate.call_args.kwargs["context"]
        self.assertIn("Prefer concise answers.", context)
        self.assertIn("Use an everyday example.", context)
        self.assertIn("I study biology.", context)
        memory.enabled = False
        memory.save()
        with patch("lightchat.views.get_provider") as get_provider:
            get_provider.return_value.generate.return_value = "Another answer."
            self.generate(prompt="Explain diffusion.")
        self.assertNotIn("I study biology.", get_provider.return_value.generate.call_args.kwargs["context"])


class ChatSettingsAndFeedbackTests(LightChatTestCase):
    def test_chat_detail_renders_model_picker_and_message_composer(self):
        response = self.client.get(reverse("chat-detail", args=[self.chat.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="model-picker"')
        self.assertContains(response, 'id="prompt-form"')
        self.assertContains(response, "mock-google-premium")

    def test_chats_can_be_created_renamed_archived_and_deleted(self):
        response = self.client.post(reverse("create-chat"), {"title": "Research notes"})
        created = ChatSession.objects.get(owner=self.user, title="Research notes")
        self.assertRedirects(response, reverse("chat-detail", args=[created.id]))
        response = self.client.post(reverse("rename-chat", args=[created.id]), {"title": "Reading notes"})
        self.assertRedirects(response, reverse("chat-detail", args=[created.id]))
        created.refresh_from_db()
        self.assertEqual(created.title, "Reading notes")
        self.client.post(reverse("archive-chat", args=[created.id]))
        created.refresh_from_db()
        self.assertTrue(created.archived)
        self.client.post(reverse("delete-chat", args=[created.id]))
        self.assertFalse(ChatSession.objects.filter(id=created.id).exists())

    def test_chat_ownership_is_enforced(self):
        other = User.objects.create_user(username="other", password="ClassroomPass-2048")
        provision_account(other, "Other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("chat-detail", args=[self.chat.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("delete-chat", args=[self.chat.id])).status_code, 404)

    def test_chat_instructions_and_memory_controls_persist(self):
        self.client.post(
            reverse("chat-instructions", args=[self.chat.id]),
            {"system_instructions": "Use examples from daily life."},
        )
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.system_instructions, "Use examples from daily life.")
        self.client.post(reverse("save-memory"), {"content": "I like short answers.", "enabled": "on"})
        memory = MemoryItem.objects.get(user=self.user)
        self.client.post(reverse("toggle-memory", args=[memory.id]))
        memory.refresh_from_db()
        self.assertFalse(memory.enabled)
        self.client.post(reverse("delete-memory", args=[memory.id]))
        self.assertFalse(MemoryItem.objects.filter(id=memory.id).exists())

    def test_feedback_is_saved_for_owner_response(self):
        response = self.generate()
        message_id = response.json()["message"]["id"]
        feedback_response = self.client.post(
            reverse("submit-feedback", args=[message_id]), {"rating": "up", "comment": "Clear demo."}
        )
        self.assertRedirects(feedback_response, reverse("chat-detail", args=[self.chat.id]))
        feedback = Feedback.objects.get(message_id=message_id)
        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.comment, "Clear demo.")


class UploadTests(LightChatTestCase):
    def test_text_file_is_extracted_stored_and_download_is_owner_scoped(self):
        uploaded = SimpleUploadedFile("notes.txt", b"A small document for LightChat.", content_type="text/plain")
        response = self.generate(files=[uploaded])
        self.assertEqual(response.status_code, 200)
        attachment = Attachment.objects.get()
        self.assertEqual(attachment.extracted_text, "A small document for LightChat.")
        self.assertTrue(attachment.file.name.startswith(f"uploads/{self.user.id}/"))
        self.assertEqual(self.client.get(reverse("download-attachment", args=[attachment.id])).status_code, 200)
        other = User.objects.create_user(username="reader", password="ClassroomPass-2048")
        provision_account(other, "Reader")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("download-attachment", args=[attachment.id])).status_code, 404)

    def test_pdf_is_parsed_locally(self):
        pdf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(pdf)
        uploaded = SimpleUploadedFile("blank.pdf", pdf.getvalue(), content_type="application/pdf")
        response = self.generate(files=[uploaded])
        self.assertEqual(response.status_code, 200)
        attachment = Attachment.objects.get()
        self.assertEqual(attachment.content_type, "application/pdf")
        self.assertIn("no extractable text", attachment.extracted_text)

    def test_png_requires_image_capability_before_charge(self):
        image = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image, format="PNG")
        upload = SimpleUploadedFile("diagram.png", image.getvalue(), content_type="image/png")
        with patch("lightchat.views.get_provider") as get_provider:
            rejected = self.generate(key="mock-anthropic-mid", files=[upload])
        self.assertEqual(rejected.status_code, 400)
        get_provider.assert_not_called()
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 100)
        self.assertEqual(GenerationRequest.objects.count(), 0)

        image.seek(0)
        upload = SimpleUploadedFile("diagram.png", image.getvalue(), content_type="image/png")
        accepted = self.generate(key="mock-openai-vision", files=[upload])
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(Attachment.objects.get().is_image)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 97)

        jpeg = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(jpeg, format="JPEG")
        upload = SimpleUploadedFile("photo.jpeg", jpeg.getvalue(), content_type="image/jpeg")
        accepted = self.generate(key="mock-openai-vision", files=[upload], prompt="Review this image.")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(Attachment.objects.filter(is_image=True).count(), 2)

    @override_settings(LIGHTCHAT_MAX_UPLOAD_BYTES=8)
    def test_configured_size_limit_is_enforced(self):
        upload = SimpleUploadedFile("too-large.txt", b"more than eight", content_type="text/plain")
        response = self.generate(files=[upload])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 100)

    def test_unsupported_type_is_rejected(self):
        upload = SimpleUploadedFile("script.html", b"<script>alert(1)</script>", content_type="text/html")
        response = self.generate(files=[upload])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Attachment.objects.count(), 0)

    def test_oversized_file_is_rejected_before_reading_content(self):
        class OversizedUpload:
            name = "too-large.txt"
            size = 20_000_000

            def read(self, _limit):
                raise AssertionError("The upload body must not be read after the size check fails.")

        from .services import UploadValidationError, prepare_attachments

        with override_settings(LIGHTCHAT_MAX_UPLOAD_BYTES=1024):
            with self.assertRaises(UploadValidationError):
                prepare_attachments([OversizedUpload()])

    def test_user_deletion_removes_local_media(self):
        uploaded = SimpleUploadedFile("notes.txt", b"Private classroom file.", content_type="text/plain")
        self.assertEqual(self.generate(files=[uploaded]).status_code, 200)
        attachment = Attachment.objects.get()
        stored_path = attachment.file.path
        self.assertTrue(os.path.exists(stored_path))
        self.user.delete()
        self.assertFalse(os.path.exists(stored_path))


class ClassroomSmokeTests(LightChatTestCase):
    def test_complete_mock_backed_classroom_flow(self):
        self.client.logout()
        signup_response = self.client.post(
            reverse("signup"),
            {
                "username": "classroom-user",
                "display_name": "Classroom User",
                "password1": "LongClassroomPass-5102",
                "password2": "LongClassroomPass-5102",
            },
        )
        self.assertEqual(signup_response.status_code, 302)
        user = User.objects.get(username="classroom-user")
        first_chat_response = self.client.post(reverse("create-chat"), {"title": "Course notes"})
        chat = ChatSession.objects.get(owner=user, title="Course notes")
        self.assertEqual(first_chat_response.status_code, 302)
        self.client.post(reverse("global-prompt"), {"global_system_prompt": "Explain one idea at a time."})
        self.client.post(reverse("save-memory"), {"content": "I am studying ecology.", "enabled": "on"})

        text_upload = SimpleUploadedFile("outline.txt", b"A habitat supports living things.", content_type="text/plain")
        first = self.client.post(
            reverse("generate", args=[chat.id]),
            {
                "prompt": "Summarize this outline.",
                "model_key": "mock-openai-low",
                "request_id": str(uuid4()),
                "files": [text_upload],
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["balance"], 99)

        second = self.client.post(
            reverse("generate", args=[chat.id]),
            {
                "prompt": "Give one follow-up question.",
                "model_key": "mock-google-premium",
                "request_id": str(uuid4()),
            },
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["balance"], 94)
        self.client.post(
            reverse("submit-feedback", args=[second.json()["message"]["id"]]),
            {"rating": "up", "comment": "Useful structure."},
        )

        settings_response = self.client.get(reverse("settings"))
        self.assertContains(settings_response, "Classroom User")
        self.assertContains(settings_response, "I am studying ecology.")
        self.assertContains(settings_response, "-5")
        self.assertEqual(Feedback.objects.filter(user=user).count(), 1)
        self.assertEqual(chat.messages.count(), 4)

        second_chat_response = self.client.post(reverse("create-chat"), {"title": "Draft"})
        second_chat = ChatSession.objects.get(owner=user, title="Draft")
        self.assertEqual(second_chat_response.status_code, 302)
        self.client.post(reverse("rename-chat", args=[second_chat.id]), {"title": "Working draft"})
        self.assertEqual(self.client.get(reverse("chat-detail", args=[chat.id])).status_code, 200)
