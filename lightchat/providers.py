import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .catalog import THINKING_EFFORTS


class ProviderError(Exception):
    def __init__(self, message, *, status=502, code="provider_error"):
        super().__init__(message)
        self.status = status
        self.code = code


class MockProviderError(ProviderError):
    pass


class DeterministicMockProvider:
    """Produce an explicit demo response without making a network request."""

    def generate(self, *, option, prompt, context, attachments, thinking_effort="medium"):
        if "[[mock-error]]" in prompt:
            raise MockProviderError("The mock provider was asked to simulate a failure.", code="mock_provider_error")

        files = ", ".join(attachment["name"] for attachment in attachments) or "none"
        context_note = "Your saved instructions and recent messages were included." if context else "No saved context was added."
        return (
            f"Mock response for the {option['provider_label']} target ({option['tier']} demo model).\n\n"
            f"Prompt received: {prompt.strip()}\n\n"
            f"Attachments received: {files}. {context_note}\n\n"
            "This deterministic response confirms that LightChat routed the request through its mock provider. "
            "It is not a response from the real provider."
        )


class LiteChatProxyProvider:
    provider_paths = {
        "openai": "/openai/v1/chat/completions",
        "anthropic": "/anthropic/v1/messages",
    }

    def __init__(self, *, proxy_url, api_keys, timeout=45):
        self.proxy_url = (proxy_url or "https://proxy.litechat.ai").rstrip("/")
        self.api_keys = api_keys
        self.timeout = timeout
        parsed = urlsplit(self.proxy_url)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if (
            parsed.scheme != "https"
            or parsed.hostname != "proxy.litechat.ai"
            or port not in {None, 443}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderError("The LiteChat proxy URL must use the documented HTTPS host.", status=503, code="invalid_proxy_url")

    def generate(self, *, option, prompt, context, attachments, thinking_effort="medium"):
        provider = option["provider"]
        model = option.get("upstream_model_id")
        credential = self.api_keys.get(provider, "")
        if thinking_effort not in THINKING_EFFORTS:
            raise ProviderError("Choose a valid thinking effort.", status=400, code="invalid_thinking_effort")
        if not model:
            raise ProviderError("This model is available only in mock mode.", status=400, code="mock_only_model")
        if not credential:
            raise ProviderError("The server is missing a credential for this provider.", status=503, code="missing_credential")

        payload = self.build_payload(
            provider,
            model,
            prompt,
            context,
            attachments,
            thinking_effort=thinking_effort,
            supports_thinking_effort=option.get("supports_thinking_effort", False),
        )
        if provider == "openai":
            url = self.proxy_url + self.provider_paths[provider]
            headers = {"Authorization": f"Bearer {credential}"}
        elif provider == "anthropic":
            url = self.proxy_url + self.provider_paths[provider]
            headers = {
                "x-api-key": credential,
                "anthropic-version": "2023-06-01",
            }
        elif provider == "google":
            url = self.proxy_url + f"/google/v1beta/models/{quote(model, safe='-._')}:generateContent"
            headers = {"x-goog-api-key": credential}
        else:
            raise ProviderError("This provider is not supported in LiteChat mode.", status=400, code="unsupported_provider")

        return self._read_text(provider, self._post_json(url, headers, payload))

    @staticmethod
    def build_payload(
        provider,
        model,
        prompt,
        context,
        attachments,
        *,
        thinking_effort="medium",
        supports_thinking_effort=False,
    ):
        images = [attachment for attachment in attachments if attachment.get("is_image")]
        if images and not MODEL_IMAGE_SUPPORT.get(provider, False):
            raise ProviderError("The selected provider model does not support images.", status=400, code="unsupported_image")
        if any(not image.get("image_data") for image in images):
            raise ProviderError("An attached image could not be read.", status=400, code="invalid_image")

        if provider == "openai":
            messages = [{"role": "system", "content": context}] if context else []
            content = [{"type": "text", "text": prompt}]
            content.extend(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{attachment['content_type']};base64,{attachment['image_data']}",
                        "detail": "auto",
                    },
                }
                for attachment in images
            )
            messages.append({"role": "user", "content": content if images else prompt})
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 512,
            }
            if supports_thinking_effort:
                payload["reasoning_effort"] = thinking_effort
            return payload

        if provider == "anthropic":
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": attachment["content_type"],
                        "data": attachment["image_data"],
                    },
                }
                for attachment in images
            ]
            content.append({"type": "text", "text": prompt})
            payload = {
                "model": model,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": content if images else prompt}],
                "thinking": {"type": "disabled"},
            }
            if context:
                payload["system"] = context
            return payload

        if provider == "google":
            parts = [{"text": prompt}]
            parts.extend(
                {
                    "inlineData": {
                        "mimeType": attachment["content_type"],
                        "data": attachment["image_data"],
                    }
                }
                for attachment in images
            )
            generation_config = {"maxOutputTokens": 512}
            if supports_thinking_effort:
                generation_config["thinkingConfig"] = {"thinkingLevel": thinking_effort.upper()}
            payload = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": generation_config,
            }
            if context:
                payload["systemInstruction"] = {"parts": [{"text": context}]}
            return payload

        raise ProviderError("This provider is not supported in LiteChat mode.", status=400, code="unsupported_provider")

    def _post_json(self, url, headers, payload):
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        for name, value in headers.items():
            request.add_unredirected_header(name, value)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as error:
            status = 429 if error.code == 429 else 502
            code = f"litechat_http_{error.code}"
            message = {
                400: "LiteChat rejected the provider request. Check the selected model and inputs.",
                401: "LiteChat rejected the provider credential. Check the server-side credential configuration.",
                403: "LiteChat denied access to this provider. Check credential access.",
                429: "LiteChat is rate-limited. Wait briefly before you try again.",
                502: "The upstream provider is temporarily unavailable.",
                503: "The LiteChat service is unavailable.",
                504: "The upstream provider request timed out.",
            }.get(error.code, "The LiteChat provider request failed.")
            raise ProviderError(message, status=status, code=code) from None
        except (URLError, TimeoutError, socket.timeout):
            raise ProviderError("The LiteChat proxy could not be reached.", status=502, code="proxy_unreachable") from None

        if len(body) > 4 * 1024 * 1024:
            raise ProviderError("The provider response exceeded the supported size.", code="response_too_large")
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProviderError("LiteChat returned an invalid JSON response.", code="invalid_json") from None

    @staticmethod
    def _read_text(provider, response):
        if provider == "openai":
            choices = response.get("choices") or []
            if not choices:
                raise ProviderError("OpenAI returned no response choices.", code="empty_response")
            choice = choices[0]
            if choice.get("finish_reason") in {"length", "tool_calls"}:
                raise ProviderError("OpenAI did not complete a text response.", code="incomplete_response")
            content = choice.get("message", {}).get("content", "")
            if isinstance(content, list):
                content = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
        elif provider == "anthropic":
            if response.get("stop_reason") in {"max_tokens", "tool_use"}:
                raise ProviderError("Anthropic did not complete a text response.", code="incomplete_response")
            content = "\n".join(block.get("text", "") for block in response.get("content", []) if block.get("type") == "text")
        else:
            candidates = response.get("candidates") or []
            if not candidates:
                raise ProviderError("Google returned no response candidates.", code="empty_response")
            candidate = candidates[0]
            if candidate.get("finishReason") in {"MAX_TOKENS", "SAFETY", "RECITATION"}:
                raise ProviderError("Google did not complete a text response.", code="incomplete_response")
            content = "\n".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []) if "text" in part)

        if not isinstance(content, str) or not content.strip():
            raise ProviderError("The provider returned no text response.", code="empty_response")
        return content.strip()


MODEL_IMAGE_SUPPORT = {"openai": True, "anthropic": True, "google": True}


def get_provider(mode, *, proxy_url="", api_keys=None):
    if mode == "mock":
        return DeterministicMockProvider()
    if mode == "litechat":
        return LiteChatProxyProvider(proxy_url=proxy_url, api_keys=api_keys or {})
    return None
