# LiteChat Real Provider Integration Plan

- **Status:** Ready for execution. No provider-integration code has been changed.
- **Created:** 2026-09-29 (Unix timestamp `1790671297`)
- **Study:** `doc/study/1790670223_litechat-real-provider-contract.md`
- **Scope:** Replace LightChat's real-provider 503 response with documented LiteChat proxy calls for OpenAI, Anthropic, and Google.
- **Suggested plan commit:** `docs: plan LiteChat live provider integration`

## Objective

Implement real model requests through `https://proxy.litechat.ai/` using the verified LiteChat API contract. Keep the deterministic mock path for tests and demos. Preserve account credit checks, per-request simulated costs, chat persistence, model selection, global and per-chat instructions, file handling, feedback, and safe failure behavior.

## Resolved Contract

| Provider | Endpoint | Upstream model | Credential header | Response text |
| --- | --- | --- | --- | --- |
| OpenAI | `/openai/v1/chat/completions` | `gpt-5.6-luna` | `Authorization: Bearer <key>` | `choices[0].message.content` |
| Anthropic | `/anthropic/v1/messages` | `claude-haiku-4-5-20251001` | `x-api-key` plus `anthropic-version: 2023-06-01` | Text blocks in `content` |
| Google | `/google/v1beta/models/gemini-3.8-flash:generateContent` | `gemini-3.8-flash` | `x-goog-api-key` | Text parts in `candidates[0].content.parts` |

Use non-streaming JSON requests. The proxy does not run application tools. Do not execute tool calls. Do not retry requests automatically after a provider request may have completed.

## Credential and Worktree Rules

- Read the existing `.env` credential variables through settings. Do not open, print, log, test-dump, or commit their values.
- Keep `LIGHTCHAT_PROVIDER_MODE=mock` as the default. Real calls use `LIGHTCHAT_PROVIDER_MODE=litechat`.
- Default a blank `LITECHAT_PROXY_URL` to the documented proxy root. Keep the setting override available.
- Rename the settings mapping from `LITECHAT_CREDENTIALS` to a name that Django's debug exception filter recognizes as sensitive, such as `LITECHAT_API_KEYS`. Keep the existing `LITECHAT_OPENAI_CREDENTIAL`, `LITECHAT_ANTHROPIC_CREDENTIAL`, and `LITECHAT_GOOGLE_CREDENTIAL` environment variable names.
- The worktree has user-owned uncommitted edits in `lightchat_site/settings.py`, `lightchat/templates/registration/login.html`, and `lightchat/templates/lightchat/base.html`. Preserve them. Do not revert or include them in the provider commit. If a provider change touches `settings.py`, stage only the provider-specific hunk.
- Do not modify `.env` during implementation. Use the current values through the application's environment loader.

## Implementation Task Board

### Phase 0: Prepare

- [ ] Confirm `main` and the worktree state. Preserve the three existing uncommitted user changes listed above.
- [ ] Create a separate implementation branch from `main` before provider code changes.
- [ ] Re-read the LiteChat and image request contracts in the study. Do not add any undocumented header, route, model ID, or request option.
- [ ] Check credential availability only as booleans. Do not display values.

### Phase 1: Provider configuration and adapter

- [ ] Replace the 503-only non-mock path with a provider interface that dispatches to the deterministic mock or the LiteChat adapter.
- [ ] Add real catalogue IDs from the LiteChat docs: `gpt-5.6-luna`, `claude-haiku-4-5-20251001`, and `gemini-3.8-flash`. Keep the existing internal provider/model selection separate from endpoint and credentials.
- [ ] Retain configurable fictional per-request credit costs. Do not use provider token usage or live pricing for deductions.
- [ ] Implement the OpenAI Chat Completions request and response adapter with its documented endpoint and Bearer header.
- [ ] Implement the Anthropic Messages request and response adapter with its documented endpoint, `x-api-key`, and version header.
- [ ] Implement the Gemini Generate Content request and response adapter with its documented endpoint and `x-goog-api-key`.
- [ ] Use bounded timeouts and JSON response parsing. Map transport, auth, rate-limit, invalid-request, upstream, and malformed-response errors to safe user messages.
- [ ] Do not log request headers, credentials, raw error bodies, or user prompt contents.
- [ ] Keep the mock provider unchanged and available with no credential requirement.

### Phase 2: Conversation, files, and simulated credits

- [ ] Route real calls through the selected provider while preserving chat ownership checks, request IDs, context construction, message persistence, and response provider/model labels.
- [ ] Keep system instructions provider-specific: OpenAI `system` message, Anthropic `system` field, and Gemini `systemInstruction`.
- [ ] Continue to extract PDF/TXT content locally and include the extracted text in the prompt context.
- [ ] Serialize validated PNG/JPEG attachments using documented provider formats: OpenAI Chat Completions `image_url` data URL, Anthropic Base64 image blocks, and Gemini `inlineData` with `mimeType` and Base64 `data`.
- [ ] Keep image capability flags in the model catalogue. Reject unsupported combinations before credit reservation or provider invocation.
- [ ] Reserve/deduct the configured flat test-credit cost before a request, write the ledger record transactionally, and release the test credits on provider failure.
- [ ] Preserve existing mock-only model options and clearly show whether a response used `mock` or the LiteChat proxy.
- [ ] Keep retries idempotent. Do not automatically repeat a real-provider request with uncertain outcome.

### Phase 3: Tests and real-provider smoke checks

- [ ] Add unit tests for endpoint paths, headers, request JSON, response parsing, model selection, image payload encoding, and safe error mapping. Use synthetic test credentials only in mocked tests.
- [ ] Verify mock mode still works without provider credentials and all prior account/chat/credit/file tests pass.
- [ ] Verify real mode returns a safe error before credit deduction when the selected provider credential is missing.
- [ ] Verify provider failures release simulated test credits and never expose provider response bodies or credential values.
- [ ] Check the real credential environment variables without printing values. If credentials are available, send one minimal real text request through the LightChat proxy to each provider. Report only provider name, success/failure, and HTTP status.
- [ ] Do not perform automatic retries during live smoke checks. Do not include secrets, response text, or request headers in command output.

### Phase 4: Commit and rendezvous

- [ ] Run `.venv/bin/python manage.py check`, `.venv/bin/python manage.py makemigrations --check --dry-run`, the full Django test suite, and JavaScript syntax checks.
- [ ] Stage only provider integration changes. Keep the pre-existing edits in `settings.py`, `login.html`, and `base.html` unstaged and uncommitted.
- [ ] Commit as `feat: integrate LiteChat real providers`.
- [ ] Fast-forward merge the implementation branch to `main` and rerun checks after the merge.
- [ ] Update this plan and `TODO.md` with test, smoke-check, and merge results.

### Phase 5: Sync living docs

- [ ] Update `doc/wiki/` with the real-provider mode, selected model IDs, and server-only environment configuration.
- [ ] Update `doc/wiki/footguns/` with provider-specific image payload differences and the no-auto-retry behavior after uncertain requests.
- [ ] Keep docs based only on the proxy docs and verified implementation. Do not change `doc/canonical/`.

## Acceptance Criteria

- Mock mode still works without provider credentials.
- LiteChat mode routes selected OpenAI, Anthropic, and Google models through the documented proxy paths and provider-specific authentication headers.
- Responses from each API format are parsed and saved with the correct provider/model label.
- PDF/TXT and supported PNG/JPEG file handling remains available in the real provider path.
- Missing credentials, provider errors, timeouts, malformed responses, and unsupported tools fail safely without exposing secrets or raw provider error bodies.
- Insufficient test credits still block the provider call. Simulated model costs remain configurable and do not depend on live pricing or token usage.
- At least one real request per provider succeeds if the credentials and proxy service are available. Otherwise, report the provider and safe failure status without revealing values.
- Existing user changes in `settings.py`, `login.html`, and `base.html` remain preserved and are not included in the provider commit.
