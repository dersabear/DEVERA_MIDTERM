# LiteChat Real Provider Contract Study

- **Study date:** 2026-09-29
- **Unix timestamp:** `1790670223`
- **Purpose:** Record the verified LiteChat API contract for OpenAI, Anthropic, and Google before implementing live provider calls.
- **Status:** Research only. No application code or `.env` value was changed or printed during this study.

## Current State

LightChat already has a deterministic mock adapter and separate provider/model options. `lightchat_site/settings.py` loads one credential value per provider from the root `.env`. The generation view currently blocks all non-mock requests. The `.env` file exists locally and is ignored by Git. This study did not read its values.

Model request costs are fictional, flat per-request test-credit costs. Live provider usage and pricing must not change this rule. File uploads are stored locally; PDF and TXT content is extracted locally. Images require provider-specific request payloads.

## LiteChat Contract

The LiteChat documentation says to send JSON requests from the backend. It provides these endpoints, model IDs, authentication headers, and response locations:

| Target | Endpoint | Model ID | Required provider authentication | Response text |
| --- | --- | --- | --- | --- |
| OpenAI Chat Completions | `POST /openai/v1/chat/completions` | `gpt-5.6-luna` | `Authorization: Bearer <OpenAI credential>` | `choices[0].message.content` |
| Anthropic Messages | `POST /anthropic/v1/messages` | `claude-haiku-4-5-20251001` | `x-api-key: <Anthropic credential>` and `anthropic-version: 2023-06-01` | Text blocks in `content[]` |
| Google Gemini Generate Content | `POST /google/v1beta/models/gemini-3.8-flash:generateContent` | `gemini-3.8-flash` | `x-goog-api-key: <Google credential>` | Text parts in `candidates[0].content.parts[]` |

The shared proxy root is `https://proxy.litechat.ai`. The provider paths are different. OpenAI Chat Completions and Responses share one OpenAI credential.

### Requests

- All requests use `Content-Type: application/json`.
- OpenAI uses a `messages` array. Its example uses `max_tokens` and `reasoning_effort: "none"`. Previous turns can be sent as messages.
- Anthropic uses `messages`, the separate `system` field for instructions, `max_tokens`, and a version header. Its example disables thinking with `{"type":"disabled"}`.
- Gemini uses `contents` with `role` and `parts`, `systemInstruction` for instructions, and `generationConfig.maxOutputTokens`. Its example disables thinking with `generationConfig.thinkingConfig.thinkingBudget: 0`.
- The proxy documentation shows whole JSON responses as the normal request. Streaming is optional. LightChat's existing request/response UI is synchronous, so the MVP can use non-streaming requests.
- The proxy does not execute application functions. Function/tool calls must not be run by LightChat. Return a clear unsupported-tool error if a response contains only a tool call.

### Responses

- OpenAI Chat Completions returns text in `choices[0].message.content`. `finish_reason` can be `stop`, `length`, or `tool_calls`.
- Anthropic returns content blocks. Join blocks with type `text`. `stop_reason` can indicate normal completion, output truncation, or a tool request.
- Google returns candidate parts. Join parts with a `text` value. `finishReason` can indicate normal stop, token limit, or a safety block.
- Check for missing or empty text and incomplete/tool outcomes. Do not treat these as successful responses.
- Keep provider error response bodies private. Report safe errors without request headers, credentials, or raw bodies.

### Errors and retry policy

- LiteChat documents `400` for invalid requests, `401/403` for key/provider/expiry or authorization issues, and `429` for rate limiting.
- It documents `502/504` for upstream failures and recommends contacting the administrator for persistent `503` failures.
- Usage can be unknown after an upstream failure. Do not automatically retry a provider request after the request may have reached the proxy.
- On provider failure, keep LightChat's existing behavior: release the reserved test credits and record a failed generation. Do not add real billing or live usage-based prices.

## Image and File Inputs

LiteChat states that image inputs and provider file APIs are available. LightChat does not need provider file APIs for PDF or TXT. It already extracts these files locally, applies a size limit, and stores them in local media. Include extracted text in each real provider request.

Provider image formats differ:

- **OpenAI Chat Completions:** Its API schema defines user message image parts as `{"type":"image_url","image_url":{"url":"data:<mime>;base64,<data>","detail":"auto"}}`. Use a Base64 data URL from the validated local PNG/JPEG attachment.
- **Anthropic Messages:** Use an image content block with `source.type="base64"`, the validated image's `media_type`, and Base64 `data`. Place the system prompt in the separate `system` field.
- **Google Gemini:** Use a content part with `inlineData.mimeType` and Base64 `inlineData.data`. The LiteChat example documents text parts. The Google REST schema documents `inlineData`; the LiteChat call should be verified with a real request before this image capability is presented as tested.

The selected LiteChat model IDs are documented as image-capable through provider image interfaces. Keep the capability flag in the configurable model catalogue. If image serialization fails validation, do not call the provider. If a provider rejects its documented image part, release credits and show a safe error.

## Integration Design

Use one LiteChat adapter that maps the selected target provider to its documented path, headers, request serializer, and response parser. Keep these mappings separate from the model catalogue and keep the mock adapter as the fallback for tests and demos.

Use the existing local environment variable names:

- `LITECHAT_PROXY_URL`, defaulting to the documented root when blank.
- `LITECHAT_OPENAI_CREDENTIAL`.
- `LITECHAT_ANTHROPIC_CREDENTIAL`.
- `LITECHAT_GOOGLE_CREDENTIAL`.
- `LIGHTCHAT_PROVIDER_MODE=mock` by default; `litechat` selects real provider requests.

Read credential values only on the server. Do not print them, add them to templates, return them to the browser, or commit them. The real smoke test must report only provider name and pass/fail status. Keep per-request credit charges based on `lightchat/catalog.py`, not tokens or live vendor prices.

## Sources

- LiteChat overview and authentication: <https://proxy.litechat.ai/docs>
- LiteChat OpenAI Chat Completions: <https://proxy.litechat.ai/docs/openai/chat-completions>
- LiteChat Anthropic Messages: <https://proxy.litechat.ai/docs/anthropic/messages>
- LiteChat Google Gemini Generate Content: <https://proxy.litechat.ai/docs/google/gemini>
- OpenAI API image input guide: <https://developers.openai.com/api/docs/guides/images-vision>
- OpenAI Chat Completions API schema: <https://github.com/openai/openai-openapi/blob/master/openapi.yaml>
- Anthropic image input guide: <https://platform.claude.com/docs/en/build-with-claude/vision>
- Google Generative Language REST schema: <https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta>
- Google Gemini 3.8 Flash guide: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash>
