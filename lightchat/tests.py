import os
import json
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4
from wsgiref.util import setup_testing_defaults

from django.conf import settings
from django.core.handlers.wsgi import WSGIHandler
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import get_commands, load_command_class
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import override_script_prefix
from django.urls import reverse
from django.views.debug import SafeExceptionReporterFilter
from PIL import Image
from pypdf import PdfWriter

from .catalog import MODEL_OPTIONS, get_model_option, get_model_options
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
from .management.commands.runserver import ScriptNameAwareStaticFilesHandler
from lightchat_site.settings import parse_allowed_hosts
from lightchat.providers import LiteChatProxyProvider, ProviderError
from .middleware import resolve_script_name

User = get_user_model()


class CodeRangeAllowedHostsTests(SimpleTestCase):
    def test_dynamic_forwarded_host_is_accepted_in_local_debug_mode(self):
        self.assertIn("*", settings.ALLOWED_HOSTS)
        forwarded_host = f"session-{uuid4().hex}.preview.coderange.test"
        response = Client().get("/", HTTP_HOST=forwarded_host)
        self.assertEqual(response.status_code, 302)

    def test_wildcard_is_rejected_outside_debug_mode(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            parse_allowed_hosts("127.0.0.1,localhost,*", debug=False)

    def test_explicit_hosts_are_retained(self):
        self.assertEqual(
            parse_allowed_hosts("localhost, example.test", debug=False),
            ["localhost", "example.test"],
        )

    def test_forwarded_prefix_is_dynamic_validated_and_debug_only(self):
        prefix = f"/proxy/{20000 + int(uuid4().hex[:4], 16) % 40000}"
        with override_settings(LIGHTCHAT_BASE_PATH=""):
            self.assertEqual(resolve_script_name({"HTTP_X_FORWARDED_PREFIX": prefix}, debug=True), prefix)
            self.assertEqual(resolve_script_name({"HTTP_X_FORWARDED_PREFIX": prefix}, debug=False), "")
            self.assertEqual(resolve_script_name({"SCRIPT_NAME": prefix}, debug=False), prefix)
            self.assertEqual(resolve_script_name({"HTTP_X_FORWARDED_PREFIX": "https://example.test"}, debug=True), "")
            self.assertEqual(resolve_script_name({"HTTP_X_FORWARDED_PREFIX": "/../other"}, debug=True), "")
        with override_settings(LIGHTCHAT_BASE_PATH=prefix):
            self.assertEqual(resolve_script_name({}, debug=False), prefix)
            self.assertEqual(
                resolve_script_name({"SCRIPT_NAME": f"{prefix}{prefix}"}, debug=False),
                prefix,
            )
            self.assertEqual(
                resolve_script_name({"HTTP_X_FORWARDED_PREFIX": f"{prefix}{prefix}"}, debug=True),
                prefix,
            )


@override_settings(
    DEBUG=True,
    STATIC_URL="/static/",
    LIGHTCHAT_PROVIDER_MODE="mock",
    LIGHTCHAT_BASE_PATH="",
    SESSION_COOKIE_PATH="/",
    CSRF_COOKIE_PATH="/",
)
class ForwardedStaticAssetTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media.name)
        self.media_override.enable()
        self.user = User.objects.create_user(username="forwarded-user", password="ForwardedPass-7031")
        provision_account(self.user, "Forwarded User")

    def tearDown(self):
        self.media_override.disable()
        self.media.cleanup()

    def test_login_links_and_assets_include_dynamic_script_name(self):
        prefix = f"/proxy/{20000 + int(uuid4().hex[:4], 16) % 40000}"
        with override_script_prefix(prefix):
            page = Client().get("/login/", SCRIPT_NAME=prefix)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertIn(f'href="{prefix}/static/lightchat/app.css"', html)
        self.assertIn(f'src="{prefix}/static/lightchat/app.js"', html)
        self.assertIn("Create an account", html)
        self.assertIn('id="id_username"', html)
        self.assertIn('class="auth-layout"', html)
        self.assertEqual(get_commands()["runserver"], "lightchat")
        runserver = load_command_class("lightchat", "runserver")
        self.assertIsInstance(
            runserver.get_handler(use_static_handler=True, insecure_serving=False),
            ScriptNameAwareStaticFilesHandler,
        )

        with override_script_prefix(prefix):
            login_response = self.client.post(
                "/login/",
                {"username": "forwarded-user", "password": "ForwardedPass-7031"},
                SCRIPT_NAME=prefix,
            )
            home_response = self.client.get("/", SCRIPT_NAME=prefix)
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response["Location"], f"{prefix}/")
        self.assertEqual(home_response.status_code, 200)

        for name, content_type in [
            ("app.css", "text/css"),
            ("app.js", "text/javascript"),
        ]:
            status, headers, body = self.fetch_static(
                f"/static/lightchat/{name}", script_name=prefix
            )
            self.assertEqual(status, "200 OK")
            self.assertTrue(dict(headers)["Content-Type"].startswith(content_type))
            self.assertTrue(body)

    def test_assets_still_work_without_a_mount_prefix(self):
        for name in ("app.css", "app.js"):
            status, _headers, body = self.fetch_static(
                f"/static/lightchat/{name}", script_name=""
            )
            self.assertEqual(status, "200 OK")
            self.assertTrue(body)

    def test_forwarded_static_handler_serves_stripped_and_unstripped_prefix_paths(self):
        prefix = self.dynamic_prefix()
        for name in ("app.css", "app.js"):
            for path in (
                f"/static/lightchat/{name}",
                f"{prefix}/static/lightchat/{name}",
            ):
                status, _headers, body = self.fetch_static(
                    path,
                    script_name="",
                    forwarded_prefix=prefix,
                )
                self.assertEqual(status, "200 OK")
                self.assertTrue(body)

    def test_forwarded_prefix_header_covers_auth_routes_and_keeps_local_root(self):
        prefix = self.dynamic_prefix()
        page = self.client.get("/login/", HTTP_X_FORWARDED_PREFIX=prefix)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertIn(f'href="{prefix}/static/lightchat/app.css"', html)
        self.assertIn(f'src="{prefix}/static/lightchat/app.js"', html)
        self.assertIn(f'action="{prefix}/login/"', html)
        self.assertIn(f'href="{prefix}/signup/"', html)

        unstripped_page = self.client.get(
            f"{prefix}/login/",
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(unstripped_page.status_code, 200)
        self.assertIn(f'href="{prefix}/static/lightchat/app.css"', unstripped_page.content.decode())

        login_response = self.client.post(
            "/login/",
            {"username": "forwarded-user", "password": "ForwardedPass-7031"},
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response["Location"], f"{prefix}/")
        self.assertEqual(self.client.get("/", HTTP_X_FORWARDED_PREFIX=prefix).status_code, 200)

        logout_response = self.client.post(reverse("logout"), HTTP_X_FORWARDED_PREFIX=prefix)
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response["Location"], f"{prefix}/login/")

        signup_page = self.client.get("/signup/", HTTP_X_FORWARDED_PREFIX=prefix)
        self.assertContains(signup_page, f'action="{prefix}/signup/"')
        signup_response = self.client.post(
            "/signup/",
            {
                "username": f"forwarded-{uuid4().hex[:8]}",
                "display_name": "Forwarded Signup",
                "password1": "LongClassroomPass-4048",
                "password2": "LongClassroomPass-4048",
            },
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(signup_response.status_code, 302)
        self.assertEqual(signup_response["Location"], f"{prefix}/")

        local_page = Client().get("/login/")
        self.assertContains(local_page, 'href="/static/lightchat/app.css"')
        self.assertContains(local_page, 'action="/login/"')
        self.assertContains(local_page, 'href="/signup/"')

    def test_blank_base_path_keeps_local_chat_urls_at_root(self):
        with override_settings(LIGHTCHAT_BASE_PATH=""):
            page = Client().get("/login/")
            self.assertContains(page, 'action="/login/"')
            self.assertContains(page, 'href="/static/lightchat/app.css"')
            self.assertEqual(page.cookies[settings.CSRF_COOKIE_NAME]["path"], "/")

            chat = ChatSession.objects.create(owner=self.user, title="Local route checks")
            client = Client()
            client.force_login(self.user)
            detail = client.get(reverse("chat-detail", args=[chat.id]))
            self.assertEqual(detail.status_code, 200)
            html = detail.content.decode()
            self.assertIn(f'data-generate-url="/chats/{chat.id}/generate/"', html)
            self.assertIn('action="/chats/new/"', html)

    def test_configured_base_path_prefixes_urls_redirects_and_static_assets(self):
        prefix = "/proxy/8000"
        with override_settings(
            LIGHTCHAT_BASE_PATH=prefix,
            SESSION_COOKIE_PATH=prefix,
            CSRF_COOKIE_PATH=prefix,
        ):
            client = Client()
            login_page = client.get("/login/")
            self.assertEqual(login_page.status_code, 200)
            login_html = login_page.content.decode()
            self.assertIn(f'action="{prefix}/login/"', login_html)
            self.assertIn(f'href="{prefix}/signup/"', login_html)
            self.assertIn(f'href="{prefix}/static/lightchat/app.css"', login_html)
            self.assertIn(f'src="{prefix}/static/lightchat/app.js"', login_html)
            self.assertEqual(login_page.cookies[settings.CSRF_COOKIE_NAME]["path"], prefix)

            for environ in (
                {"SCRIPT_NAME": f"{prefix}{prefix}"},
                {"HTTP_X_FORWARDED_PREFIX": f"{prefix}{prefix}"},
            ):
                duplicate_signal_client = Client()
                duplicate_signal_page = duplicate_signal_client.get("/login/", **environ)
                self.assertEqual(duplicate_signal_page.status_code, 200)
                duplicate_html = duplicate_signal_page.content.decode()
                self.assertIn(f'href="{prefix}/static/lightchat/app.css"', duplicate_html)
                self.assertIn(f'action="{prefix}/login/"', duplicate_html)
                duplicate_login = duplicate_signal_client.post(
                    "/login/",
                    {"username": "forwarded-user", "password": "ForwardedPass-7031"},
                    **environ,
                )
                self.assertEqual(duplicate_login["Location"], f"{prefix}/")

            duplicate_path_client = Client()
            duplicate_path_page = duplicate_path_client.get(f"{prefix}{prefix}/login/")
            self.assertEqual(duplicate_path_page.status_code, 200)
            duplicate_path_html = duplicate_path_page.content.decode()
            self.assertIn(f'href="{prefix}/static/lightchat/app.css"', duplicate_path_html)
            self.assertIn(f'action="{prefix}/login/"', duplicate_path_html)
            duplicate_path_login = duplicate_path_client.post(
                f"{prefix}{prefix}/login/",
                {"username": "forwarded-user", "password": "ForwardedPass-7031"},
            )
            self.assertEqual(duplicate_path_login["Location"], "/")
            self.assertEqual(self.browser_location(duplicate_path_login, prefix), f"{prefix}/")

            login_response = client.post(
                "/login/",
                {"username": "forwarded-user", "password": "ForwardedPass-7031"},
            )
            self.assertEqual(login_response.status_code, 302)
            self.assertEqual(login_response.cookies[settings.SESSION_COOKIE_NAME]["path"], prefix)
            self.assertEqual(login_response["Location"], "/")
            self.assertEqual(self.browser_location(login_response, prefix), f"{prefix}/")

            create_response = client.post(reverse("create-chat"), {"title": "Configured base path"})
            chat = ChatSession.objects.get(owner=self.user, title="Configured base path")
            self.assertEqual(create_response["Location"], f"/chats/{chat.id}/")
            self.assertEqual(
                self.browser_location(create_response, prefix),
                f"{prefix}/chats/{chat.id}/",
            )

            detail = client.get(reverse("chat-detail", args=[chat.id]))
            self.assertEqual(detail.status_code, 200)
            detail_html = detail.content.decode()
            self.assertIn(f'data-generate-url="{prefix}/chats/{chat.id}/generate/"', detail_html)
            self.assertIn(f'action="{prefix}/chats/{chat.id}/generate/"', detail_html)
            self.assertIn(f'action="{prefix}/chats/new/"', detail_html)
            self.assertIn(f'action="{prefix}/chats/{chat.id}/rename/"', detail_html)
            self.assertIn(f'action="{prefix}/chats/{chat.id}/archive/"', detail_html)
            self.assertIn(f'action="{prefix}/chats/{chat.id}/delete/"', detail_html)
            self.assertIn(f'href="{prefix}/settings/"', detail_html)

            generated = client.post(
                reverse("generate", args=[chat.id]),
                {
                    "prompt": "Check the configured API path.",
                    "model_key": "openai-gpt-5-6-luna",
                    "request_id": str(uuid4()),
                },
            )
            self.assertEqual(generated.status_code, 200)
            message_id = generated.json()["message"]["id"]
            self.assertEqual(
                generated.json()["message"]["feedback_url"],
                f"{prefix}/feedback/{message_id}/",
            )
            feedback = client.post(reverse("submit-feedback", args=[message_id]), {"rating": "up"})
            self.assertEqual(feedback["Location"], f"/chats/{chat.id}/")
            self.assertEqual(self.browser_location(feedback, prefix), f"{prefix}/chats/{chat.id}/")

            rename_response = client.post(
                reverse("rename-chat", args=[chat.id]),
                {"title": "Renamed with configured base path"},
            )
            self.assertEqual(rename_response["Location"], f"/chats/{chat.id}/")
            self.assertEqual(self.browser_location(rename_response, prefix), f"{prefix}/chats/{chat.id}/")
            settings_page = client.get(reverse("settings"))
            self.assertContains(settings_page, f'action="{prefix}/settings/profile/"')
            profile_response = client.post(
                reverse("update-profile"),
                {"username": "forwarded-user", "display_name": "Forwarded User"},
            )
            self.assertEqual(profile_response["Location"], "/settings/")
            self.assertEqual(self.browser_location(profile_response, prefix), f"{prefix}/settings/")

            second_chat_response = client.post(reverse("create-chat"), {"title": "Delete through proxy"})
            second_chat = ChatSession.objects.get(owner=self.user, title="Delete through proxy")
            self.assertEqual(
                self.browser_location(second_chat_response, prefix),
                f"{prefix}/chats/{second_chat.id}/",
            )
            archive_response = client.post(reverse("archive-chat", args=[chat.id]))
            self.assertEqual(archive_response["Location"], "/")
            self.assertEqual(self.browser_location(archive_response, prefix), f"{prefix}/")
            delete_response = client.post(reverse("delete-chat", args=[second_chat.id]))
            self.assertEqual(delete_response["Location"], "/")
            self.assertEqual(self.browser_location(delete_response, prefix), f"{prefix}/")

            logout_response = client.post(reverse("logout"))
            self.assertEqual(logout_response["Location"], "/login/")
            self.assertEqual(self.browser_location(logout_response, prefix), f"{prefix}/login/")

            for name in ("app.css", "app.js"):
                status, _headers, body = self.fetch_static(
                    f"/static/lightchat/{name}",
                    script_name="",
                )
                self.assertEqual(status, "200 OK")
                self.assertTrue(body)
                duplicate_status, _headers, duplicate_body = self.fetch_static(
                    f"{prefix}{prefix}/static/lightchat/{name}",
                    script_name="",
                )
                self.assertEqual(duplicate_status, "200 OK")
                self.assertTrue(duplicate_body)

    @staticmethod
    def browser_location(response, prefix):
        location = response["Location"]
        if location.startswith("/") and not location.startswith("//"):
            return f"{prefix}{location}"
        return location

    def test_chat_actions_redirects_and_generated_urls_include_forwarded_prefix(self):
        prefix = self.dynamic_prefix()
        chat = ChatSession.objects.create(owner=self.user, title="Route checks")
        assistant = Message.objects.create(
            session=chat,
            role=Message.Role.ASSISTANT,
            content="A saved response.",
            provider="openai",
            execution_mode=Message.ExecutionMode.MOCK,
        )
        attachment = Attachment.objects.create(
            message=assistant,
            file=SimpleUploadedFile("notes.txt", b"Saved note", content_type="text/plain"),
            original_name="notes.txt",
            content_type="text/plain",
            size=10,
        )
        auth_redirect = self.client.get(
            reverse("chat-detail", args=[chat.id]),
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(auth_redirect.status_code, 302)
        self.assertTrue(auth_redirect["Location"].startswith(f"{prefix}/login/?next="))

        self.client.force_login(self.user)
        page = self.client.get(reverse("chat-detail", args=[chat.id]), HTTP_X_FORWARDED_PREFIX=prefix)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        for route in (
            f"{prefix}/chats/new/",
            f"{prefix}/settings/",
            f"{prefix}/logout/",
            f"{prefix}/chats/{chat.id}/generate/",
            f"{prefix}/chats/{chat.id}/rename/",
            f"{prefix}/chats/{chat.id}/instructions/",
            f"{prefix}/chats/{chat.id}/archive/",
            f"{prefix}/chats/{chat.id}/delete/",
            f"{prefix}/feedback/{assistant.id}/",
            f"{prefix}/attachments/{attachment.id}/",
        ):
            self.assertIn(route, html)
        self.assertIn(f'href="{prefix}/chats/{chat.id}/"', html)

        create_response = self.client.post(
            reverse("create-chat"),
            {"title": "Created through proxy"},
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        created = ChatSession.objects.get(owner=self.user, title="Created through proxy")
        self.assertEqual(create_response["Location"], f"{prefix}/chats/{created.id}/")

        rename_response = self.client.post(
            reverse("rename-chat", args=[chat.id]),
            {"title": "Renamed through proxy"},
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(rename_response["Location"], f"{prefix}/chats/{chat.id}/")

        feedback_response = self.client.post(
            reverse("submit-feedback", args=[assistant.id]),
            {"rating": "up"},
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(feedback_response["Location"], f"{prefix}/chats/{chat.id}/")

        download = self.client.get(
            reverse("download-attachment", args=[attachment.id]),
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"Saved note")

        generated = self.client.post(
            reverse("generate", args=[chat.id]),
            {
                "prompt": "Generate a route-aware response.",
                "model_key": "openai-gpt-5-6-luna",
                "request_id": str(uuid4()),
            },
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(
            generated.json()["message"]["feedback_url"],
            f"{prefix}/feedback/{generated.json()['message']['id']}/",
        )

        settings_page = self.client.get(reverse("settings"), HTTP_X_FORWARDED_PREFIX=prefix)
        self.assertEqual(settings_page.status_code, 200)
        self.assertIn(f'action="{prefix}/settings/profile/"', settings_page.content.decode())
        self.assertIn(f'action="{prefix}/settings/global-prompt/"', settings_page.content.decode())

        archive_response = self.client.post(
            reverse("archive-chat", args=[chat.id]),
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(archive_response["Location"], f"{prefix}/")
        delete_response = self.client.post(
            reverse("delete-chat", args=[created.id]),
            HTTP_X_FORWARDED_PREFIX=prefix,
        )
        self.assertEqual(delete_response["Location"], f"{prefix}/")

    @staticmethod
    def dynamic_prefix():
        port = 20000 + int(uuid4().hex[:4], 16) % 40000
        return f"/proxy/{port}"

    @staticmethod
    def fetch_static(path, *, script_name, forwarded_prefix=""):
        application = ScriptNameAwareStaticFilesHandler(WSGIHandler())
        environ = {}
        setup_testing_defaults(environ)
        host = f"forwarded-{uuid4().hex}.test"
        environ.update(
            REQUEST_METHOD="GET",
            SCRIPT_NAME=script_name,
            PATH_INFO=path,
            HTTP_HOST=host,
            SERVER_NAME=host,
            SERVER_PORT="80",
            **{"wsgi.input": BytesIO()},
        )
        if forwarded_prefix:
            environ["HTTP_X_FORWARDED_PREFIX"] = forwarded_prefix
        response = {}
        with override_script_prefix("/"):
            body = b"".join(
                application(
                    environ,
                    lambda status, headers, exc_info=None: response.update(status=status, headers=headers),
                )
            )
        return response["status"], response["headers"], body


class FakeProxyResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class LiteChatProxyAdapterTests(SimpleTestCase):
    credentials = {
        "openai": "synthetic-openai-key",
        "anthropic": "synthetic-anthropic-key",
        "google": "synthetic-google-key",
    }

    def call_provider(self, option, response_payload, attachments=None, thinking_effort="medium"):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            captured["redirect_headers"] = request.headers.copy()
            captured["unredirected_headers"] = {
                key.lower(): value for key, value in request.unredirected_hdrs.items()
            }
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeProxyResponse(response_payload)

        provider = LiteChatProxyProvider(
            proxy_url="https://proxy.litechat.ai/",
            api_keys=self.credentials,
            timeout=4,
        )
        with patch("lightchat.providers.urlopen", side_effect=fake_urlopen):
            result = provider.generate(
                option=option,
                prompt="Reply with a short greeting.",
                context="Use one sentence.",
                attachments=attachments or [],
                thinking_effort=thinking_effort,
            )
        return result, captured

    def test_openai_chat_completions_request_and_response(self):
        option = get_model_option("openai-gpt-5-6-luna")
        result, sent = self.call_provider(
            option,
            {"choices": [{"message": {"content": "Hello."}, "finish_reason": "stop"}]},
        )
        self.assertEqual(result, "Hello.")
        self.assertEqual(sent["url"], "https://proxy.litechat.ai/openai/v1/chat/completions")
        self.assertEqual(sent["headers"]["authorization"], "Bearer synthetic-openai-key")
        self.assertNotIn("Authorization", sent["redirect_headers"])
        self.assertEqual(sent["unredirected_headers"]["authorization"], "Bearer synthetic-openai-key")
        self.assertEqual(sent["payload"]["model"], "gpt-5.6-luna")
        self.assertEqual(sent["payload"]["messages"][0]["role"], "system")
        self.assertEqual(sent["payload"]["reasoning_effort"], "medium")

    def test_anthropic_messages_request_and_response(self):
        option = get_model_option("anthropic-claude-haiku-4-5")
        result, sent = self.call_provider(
            option,
            {"content": [{"type": "text", "text": "Hello."}], "stop_reason": "end_turn"},
        )
        self.assertEqual(result, "Hello.")
        self.assertEqual(sent["url"], "https://proxy.litechat.ai/anthropic/v1/messages")
        self.assertEqual(sent["headers"]["x-api-key"], "synthetic-anthropic-key")
        self.assertEqual(sent["unredirected_headers"]["x-api-key"], "synthetic-anthropic-key")
        self.assertEqual(sent["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(sent["payload"]["system"], "Use one sentence.")
        self.assertEqual(sent["payload"]["thinking"], {"type": "disabled"})
        self.assertEqual(sent["payload"]["max_tokens"], 512)

    def test_google_generate_content_request_and_response(self):
        option = get_model_option("google-gemini-3-8-flash")
        result, sent = self.call_provider(
            option,
            {"candidates": [{"content": {"parts": [{"text": "Hello."}]}, "finishReason": "STOP"}]},
        )
        self.assertEqual(result, "Hello.")
        self.assertEqual(
            sent["url"],
            "https://proxy.litechat.ai/google/v1beta/models/gemini-3.8-flash:generateContent",
        )
        self.assertEqual(sent["headers"]["x-goog-api-key"], "synthetic-google-key")
        self.assertEqual(sent["unredirected_headers"]["x-goog-api-key"], "synthetic-google-key")
        self.assertEqual(sent["payload"]["systemInstruction"]["parts"][0]["text"], "Use one sentence.")
        self.assertEqual(sent["payload"]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "MEDIUM")

    def test_effort_levels_map_to_each_supported_provider_contract(self):
        for effort in ("low", "medium", "high"):
            with self.subTest(provider="openai", effort=effort):
                payload = LiteChatProxyProvider.build_payload(
                    "openai",
                    "gpt-5.6-luna",
                    "Hello.",
                    "",
                    [],
                    thinking_effort=effort,
                    supports_thinking_effort=True,
                )
                self.assertEqual(payload["reasoning_effort"], effort)

            with self.subTest(provider="google", effort=effort):
                payload = LiteChatProxyProvider.build_payload(
                    "google",
                    "gemini-3.8-flash",
                    "Hello.",
                    "",
                    [],
                    thinking_effort=effort,
                    supports_thinking_effort=True,
                )
                self.assertEqual(
                    payload["generationConfig"]["thinkingConfig"]["thinkingLevel"],
                    effort.upper(),
                )

            with self.subTest(provider="anthropic", effort=effort):
                payload = LiteChatProxyProvider.build_payload(
                    "anthropic", "claude-haiku-4-5-20251001", "Hello.", "", [],
                    thinking_effort=effort,
                    supports_thinking_effort=False,
                )
                self.assertEqual(payload["thinking"], {"type": "disabled"})
                self.assertEqual(payload["max_tokens"], 512)

    def test_unsupported_model_does_not_apply_selected_effort(self):
        openai = LiteChatProxyProvider.build_payload(
            "openai", "demo", "Hello.", "", [], supports_thinking_effort=False
        )
        anthropic = LiteChatProxyProvider.build_payload(
            "anthropic", "demo", "Hello.", "", [], supports_thinking_effort=False
        )
        google = LiteChatProxyProvider.build_payload(
            "google", "demo", "Hello.", "", [], supports_thinking_effort=False
        )
        self.assertNotIn("reasoning_effort", openai)
        self.assertEqual(anthropic["thinking"], {"type": "disabled"})
        self.assertNotIn("budget_tokens", anthropic["thinking"])
        self.assertNotIn("thinkingConfig", google["generationConfig"])

    def test_image_payloads_follow_each_provider_contract(self):
        attachment = {
            "name": "sample.png",
            "is_image": True,
            "content_type": "image/png",
            "image_data": "aW1hZ2U=",
        }
        openai_payload = LiteChatProxyProvider.build_payload(
            "openai", "gpt-5.6-luna", "Look at this.", "", [attachment]
        )
        self.assertEqual(
            openai_payload["messages"][0]["content"][1]["image_url"]["url"],
            "data:image/png;base64,aW1hZ2U=",
        )

        anthropic_payload = LiteChatProxyProvider.build_payload(
            "anthropic", "claude-haiku-4-5-20251001", "Look at this.", "", [attachment]
        )
        self.assertEqual(anthropic_payload["messages"][0]["content"][0]["source"]["data"], "aW1hZ2U=")

        google_payload = LiteChatProxyProvider.build_payload(
            "google", "gemini-3.8-flash", "Look at this.", "", [attachment]
        )
        self.assertEqual(google_payload["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/png")
        self.assertEqual(google_payload["contents"][0]["parts"][1]["inlineData"]["data"], "aW1hZ2U=")

    def test_http_errors_do_not_expose_response_body(self):
        error = HTTPError(
            "https://proxy.litechat.ai/openai/v1/chat/completions",
            401,
            "Unauthorized",
            {},
            BytesIO(b"synthetic-private-error-body"),
        )
        provider = LiteChatProxyProvider(
            proxy_url="https://proxy.litechat.ai",
            api_keys=self.credentials,
        )
        with patch("lightchat.providers.urlopen", side_effect=error):
            with self.assertRaises(ProviderError) as raised:
                provider.generate(
                    option=get_model_option("openai-gpt-5-6-luna"),
                    prompt="Hello.",
                    context="",
                    attachments=[],
                )
        self.assertNotIn("synthetic-private-error-body", str(raised.exception))
        self.assertNotIn("synthetic-openai-key", str(raised.exception))

    def test_api_key_setting_name_is_masked_by_django_debug_reports(self):
        safe_value = SafeExceptionReporterFilter().cleanse_setting(
            "LITECHAT_API_KEYS",
            {"openai": "synthetic-openai-key"},
        )
        self.assertNotIn("synthetic-openai-key", repr(safe_value))

    def test_proxy_url_must_remain_at_the_documented_https_root(self):
        for url in (
            "http://proxy.litechat.ai",
            "https://proxy.litechat.ai/custom-path",
            "https://example.test",
            "https://user:pass@proxy.litechat.ai",
        ):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                LiteChatProxyProvider(proxy_url=url, api_keys=self.credentials)


@override_settings(
    LIGHTCHAT_BASE_PATH="",
    LIGHTCHAT_PROVIDER_MODE="mock",
    SESSION_COOKIE_PATH="/",
    CSRF_COOKIE_PATH="/",
)
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

    def generate(
        self,
        *,
        key="openai-gpt-5-6-luna",
        prompt="Explain this idea.",
        files=None,
        request_id=None,
        thinking_effort="medium",
    ):
        return self.client.post(
            reverse("generate", args=[self.chat.id]),
            {
                "prompt": prompt,
                "model_key": key,
                "thinking_effort": thinking_effort,
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
        low = self.generate(key="openai-gpt-5-6-luna")
        mid = self.generate(key="anthropic-claude-haiku-4-5", prompt="Compare these two ideas.")
        self.assertEqual(low.status_code, 200)
        self.assertEqual(mid.status_code, 200)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 96)
        charges = list(self.user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.GENERATION_CHARGE))
        self.assertEqual(sorted(abs(item.amount) for item in charges), [1, 3])
        self.assertEqual(low.json()["message"]["execution_mode"], "mock")
        self.assertIn("not a response from the real provider", low.json()["message"]["content"])

    def test_all_three_provider_targets_return_mock_responses(self):
        for key, provider in [
            ("openai-gpt-5-6-luna", "openai"),
            ("anthropic-claude-haiku-4-5", "anthropic"),
            ("google-gemini-3-8-flash", "google"),
        ]:
            response = self.generate(key=key, prompt=f"Try {provider} target.")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["message"]["provider"], provider)
            self.assertEqual(response.json()["message"]["execution_mode"], "mock")

    def test_insufficient_credits_block_before_message_or_provider_call(self):
        AccountBalance.objects.filter(user=self.user).update(available_credits=0)
        with patch("lightchat.views.get_provider") as get_provider:
            response = self.generate(key="google-gemini-3-8-flash")
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
            model_key="openai-gpt-5-6-luna",
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
        self.assertEqual(sum(bool(option["upstream_model_id"]) for option in MODEL_OPTIONS), 3)
        self.assertEqual(
            {option["provider"]: option["supports_thinking_effort"] for option in get_model_options("litechat")},
            {"openai": True, "anthropic": False, "google": True},
        )
        self.assertTrue(
            all(not option["supports_thinking_effort"] for option in MODEL_OPTIONS if not option["upstream_model_id"])
        )

    def test_model_cost_configuration_changes_future_charges_only(self):
        original = self.generate(key="openai-gpt-5-6-luna")
        changed = tuple(
            {**option, "request_cost_credits": 2} if option["key"] == "openai-gpt-5-6-luna" else option
            for option in MODEL_OPTIONS
        )
        with patch("lightchat.catalog.MODEL_OPTIONS", changed):
            later = self.generate(key="openai-gpt-5-6-luna", prompt="A second configured request.")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(later.status_code, 200)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 97)
        self.assertEqual(
            sorted(GenerationRequest.objects.values_list("cost_credits", flat=True)),
            [1, 2],
        )

    @override_settings(LIGHTCHAT_PROVIDER_MODE="litechat", LITECHAT_API_KEYS={})
    def test_real_mode_without_a_credential_stays_unavailable_before_provider_call(self):
        with patch("lightchat.views.get_provider") as get_provider:
            response = self.generate()
        self.assertEqual(response.status_code, 503)
        get_provider.assert_not_called()
        self.assertEqual(GenerationRequest.objects.count(), 0)

    @override_settings(
        LIGHTCHAT_PROVIDER_MODE="litechat",
        LITECHAT_API_KEYS={"openai": "synthetic-openai-key"},
    )
    def test_real_openai_request_uses_proxy_and_keeps_simulated_charge(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeProxyResponse(
                {"choices": [{"message": {"content": "Real adapter response."}, "finish_reason": "stop"}]}
            )

        with patch("lightchat.providers.urlopen", side_effect=fake_urlopen):
            response = self.generate(
                key="openai-gpt-5-6-luna",
                prompt="Write one sentence.",
                thinking_effort="low",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"]["execution_mode"], "litechat")
        self.assertEqual(response.json()["cost"], 1)
        self.assertEqual(captured["url"], "https://proxy.litechat.ai/openai/v1/chat/completions")
        self.assertEqual(captured["headers"]["authorization"], "Bearer synthetic-openai-key")
        self.assertEqual(captured["payload"]["reasoning_effort"], "low")
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 99)

    def test_invalid_thinking_effort_is_rejected_before_credit_charge(self):
        response = self.generate(thinking_effort="extreme")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 100)
        self.assertEqual(GenerationRequest.objects.count(), 0)

    @override_settings(
        LIGHTCHAT_PROVIDER_MODE="litechat",
        LITECHAT_API_KEYS={"openai": "synthetic-openai-key"},
    )
    def test_real_provider_failure_releases_credits_without_exposing_error_body(self):
        error = HTTPError(
            "https://proxy.litechat.ai/openai/v1/chat/completions",
            401,
            "Unauthorized",
            {},
            BytesIO(b"synthetic-private-provider-body"),
        )
        with patch("lightchat.providers.urlopen", side_effect=error):
            response = self.generate(key="openai-gpt-5-6-luna", prompt="Write one sentence.")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("synthetic-private-provider-body", response.json()["error"])
        self.assertNotIn("synthetic-openai-key", response.json()["error"])
        self.assertEqual(AccountBalance.objects.get(user=self.user).available_credits, 100)
        generation = GenerationRequest.objects.get(user=self.user)
        self.assertEqual(generation.status, GenerationRequest.Status.FAILED)
        self.assertEqual(generation.error_code, "litechat_http_401")
        self.assertTrue(
            self.user.credit_entries.filter(entry_type=CreditLedgerEntry.EntryType.FAILED_RELEASE).exists()
        )

    @override_settings(
        LIGHTCHAT_PROVIDER_MODE="litechat",
        LITECHAT_API_KEYS={"anthropic": "synthetic-anthropic-key"},
    )
    def test_real_anthropic_request_keeps_proxy_supported_thinking_disabled(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeProxyResponse(
                {"content": [{"type": "text", "text": "Anthropic response."}], "stop_reason": "end_turn"}
            )

        with patch("lightchat.providers.urlopen", side_effect=fake_urlopen):
            response = self.generate(
                key="anthropic-claude-haiku-4-5",
                prompt="Write one sentence.",
                thinking_effort="high",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})
        self.assertNotIn("budget_tokens", captured["payload"]["thinking"])

    @override_settings(
        LIGHTCHAT_PROVIDER_MODE="litechat",
        LITECHAT_API_KEYS={"openai": "synthetic-openai-key"},
    )
    def test_real_image_upload_is_encoded_for_openai(self):
        image = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image, format="PNG")
        upload = SimpleUploadedFile("diagram.png", image.getvalue(), content_type="image/png")
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeProxyResponse(
                {"choices": [{"message": {"content": "Image received."}, "finish_reason": "stop"}]}
            )

        with patch("lightchat.providers.urlopen", side_effect=fake_urlopen):
            response = self.generate(key="openai-gpt-5-6-luna", prompt="Describe this.", files=[upload])

        self.assertEqual(response.status_code, 200)
        image_part = captured["payload"]["messages"][-1]["content"][1]
        self.assertTrue(image_part["image_url"]["url"].startswith("data:image/png;base64,"))

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
        self.assertContains(response, 'id="thinking-effort" name="thinking_effort" form="prompt-form"')
        self.assertContains(response, '<option value="medium" selected>Medium</option>', html=True)
        self.assertContains(response, 'id="thinking-effort-status"')
        self.assertContains(response, "Thinking effort: Mock mode")
        self.assertContains(response, 'id="prompt-form"')
        self.assertContains(response, "google-gemini-3-8-flash")

    @override_settings(LIGHTCHAT_PROVIDER_MODE="litechat")
    def test_real_provider_model_enables_thinking_effort_control(self):
        response = self.client.get(reverse("chat-detail", args=[self.chat.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="thinking-effort" name="thinking_effort" form="prompt-form"')
        self.assertNotContains(response, 'id="thinking-effort" name="thinking_effort" aria-label="Thinking effort" disabled')
        self.assertContains(
            response,
            'value="anthropic-claude-haiku-4-5" data-cost="3" data-images="true" data-thinking-effort="false"',
        )

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
            rejected = self.generate(key="mock-openai-text-only", files=[upload])
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
                "model_key": "openai-gpt-5-6-luna",
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
                "model_key": "google-gemini-3-8-flash",
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
