# LiteChat Proxy Integration Study

- **Study date:** 2026-09-29
- **Unix timestamp:** `1790669802`
- **Purpose:** Record the documented LiteChat proxy contract before implementing real OpenAI, Anthropic, and Google model calls.
- **Status:** Research only. No application code was changed in this study stage.

## Current Application

LightChat has a `DeterministicMockProvider`. The generation view currently returns HTTP 503 when `LIGHTCHAT_PROVIDER_MODE` is not `mock`. Settings already load a proxy base URL and separate OpenAI, Anthropic, and Google credential variables from the root `.env`. The `.env` file exists locally and is ignored by Git. This study did not read or print its values.

The app charges fictional per-request credits from `lightchat/catalog.py`. The real provider integration must keep this rule. Provider token usage must not change the simulated credit charge.

## Verified LiteChat Contract

The LiteChat documentation says to make backend HTTP requests. It says to keep credentials out of browser code and repositories. The API endpoints, model IDs, headers, and successful response fields are:

| Target | URL path | Model ID | Authentication header | Text response |
| --- | --- | --- | --- | --- |
| OpenAI Chat Completions | `/openai/v1/chat/completions` | `gpt-5.6-luna` | `Authorization: Bearer <OpenAI key>` | `choices[0].message.content` |
| Anthropic Messages | `/anthropic/v1/messages` | `claude-haiku-4-5-20251001` | `x-api-key: <Anthropic key>` and `anthropic-version: 2023-06-01` | Join `content` blocks whose type is `text` |
| Google Gemini Generate Content | `/google/v1beta/models/gemini-3.8-flash:generateContent` | `gemini-3.8-flash` in the URL path | `x-goog-api-key: <Google key>` | Join text from `candidates[0].content.parts` |

All requests use JSON and `Content-Type: application/json`. The proxy docs show non-streaming full JSON as the normal request. The MVP does not need streaming. Keep the default proxy root in configuration as `https://proxy.litechat.ai`; join the provider-specific path from the table. Do not send these credentials to browser code.

### Request formats

- **OpenAI:** Send a `messages` array. Put prior user/assistant turns in that array. The example uses `max_tokens` and `reasoning_effort: "none"`.
- **Anthropic:** Send `messages`, put instructions in the separate `system` field, set `max_tokens`, and use `thinking: {"type": "disabled"}` for the documented non-reasoning example.
- **Google:** Send `contents` with `role` and `parts`. Put instructions in `systemInstruction`. Set `generationConfig.maxOutputTokens` and `generationConfig.thinkingConfig.thinkingBudget` to `0` for the documented non-reasoning example.

The existing app stores chat history locally and resends context. Do not use provider-stored conversations or server-side thread IDs.

### Errors and retries

- `400`: correct the request. Do not retry unchanged input.
- `401` or `403`: check the matching provider key and its state. Do not print the key or proxy response body to the user or logs.
- `429`: the proxy recommends fewer overlapping requests and a bounded delay.
- `502` or `504`: the upstream request failed.
- `503` or repeated service errors: contact the proxy administrator.
- The proxy warns that usage can be unknown after a failure. Do not automatically retry after partial streamed output. The MVP uses complete JSON responses and should release simulated test credits when it cannot save a completed response.

The proxy does not execute application functions. Tool calls are outside the MVP. If a model returns a tool call, do not execute it; return a clear unsupported-tool error or a safe model-specific response error.

## File and Image Inputs

The proxy overview says image inputs and provider file APIs are available, with files private to an account/provider and expiring after one hour. LightChat stores files locally, extracts PDF and plain-text content, and currently has PNG/JPEG upload support for mock image options. Use local extraction for PDF/TXT and include extracted text in the prompt; this does not require provider file APIs.

The provider interfaces differ for image parts. The Anthropic Messages contract is documented with content blocks; Anthropic's official vision guide describes a Base64 `image` block with `source.type`, `media_type`, and `data`. OpenAI's image guide confirms image analysis in Chat Completions and Base64 data URLs, but the proxy's Chat Completions page does not show the exact image content-block payload. The Google proxy page confirms `contents[].parts[]` for text but does not show an image part. Google's REST discovery schema uses an `inlineData` part with `mimeType` and Base64 `data`, but the proxy's support for that exact shape must be verified.

Therefore, keep the existing capability check. Enable an image-capable real model only when its request shape is supported by the proxy contract and a test. Until then, keep that model's real image capability disabled and return a clear pre-request error. Do not guess unsupported image fields.

## Integration Design

Use a small provider interface that accepts the selected catalogue option, prompt, assembled context, and validated attachments. Implement one LiteChat adapter that selects the provider path, authentication header, and serializer from the option's provider. Keep the deterministic mock implementation and select it when `LIGHTCHAT_PROVIDER_MODE=mock`.

The model catalogue should use the documented model IDs and keep fictional credit costs and capability flags as application configuration. Keep `LIGHTCHAT_PROVIDER_MODE` defaulted to `mock`; real mode should fail with a safe configuration error if a required credential is missing. Keep credentials in settings loaded from server-side environment variables. Do not log request headers, credential values, or raw provider error bodies.

Do not add live price calculations, billing integrations, or provider-side chat persistence.

## Sources

- LiteChat overview and authentication: <https://proxy.litechat.ai/docs>
- LiteChat OpenAI Chat Completions: <https://proxy.litechat.ai/docs/openai/chat-completions>
- LiteChat Anthropic Messages: <https://proxy.litechat.ai/docs/anthropic/messages>
- LiteChat Google Gemini Generate Content: <https://proxy.litechat.ai/docs/google/gemini>
- Anthropic image input: <https://platform.claude.com/docs/en/build-with-claude/vision>
- OpenAI image inputs: <https://developers.openai.com/api/docs/guides/images-vision>
- Google Generative Language REST schema: <https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta>
