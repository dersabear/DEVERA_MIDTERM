# LightChat MVP Implementation Plan

- **Status:** Mock-backed MVP implemented and verified on `feat/lightchat-mvp`. Rendezvous is pending. Live-provider invocation remains blocked pending a verifiable proxy contract.
- **Created:** 2026-09-29 05:19:57 UTC
- **Study basis:** `doc/study/1790658141_llm-aggregator-feasibility.md`
- **Suggested plan commit:** `docs: plan LightChat MVP implementation`

## Resolved Decisions

- **Repository:** The workspace is initialized as a Git repository. `main` is the primary branch. Create a separate implementation branch from `main` when executing this plan; do not create it during planning.
- **Technology:** Use Python, Django, SQLite, Django templates, and simple JavaScript where needed. Keep the frontend and backend in one Django project/application. Do not add React or Vite unless implementation uncovers a clear technical need.
- **File storage:** Use local Django media storage for this classroom MVP. Make file-size limits configurable.
- **Providers:** OpenAI, Anthropic, and Google are the initial provider targets. The current workspace has no verifiable LiteChat proxy contract, so live calls are blocked. Keep provider/model selection separate from transport and build/test the complete MVP with a deterministic mock provider. Do not guess the proxy contract.
- **Local secrets:** The app will default to mock mode. Define `LIGHTCHAT_PROVIDER_MODE`, `LITECHAT_PROXY_URL`, and opaque per-provider secret variables `LITECHAT_OPENAI_CREDENTIAL`, `LITECHAT_ANTHROPIC_CREDENTIAL`, and `LITECHAT_GOOGLE_CREDENTIAL`. Load local values from a root `.env` file that Git ignores. These names do not define an authentication format; do not send them to any endpoint until its contract is verified.
- **Proxy documentation:** The user confirms that no separate LiteChat proxy documentation is available in the workspace beyond the provided provider credentials. Do not guess the proxy URL, model IDs, authentication format, or request protocol. Missing proxy details block only real-provider calls, not the mock-backed MVP or unrelated work.
- **File types:** Support PDF, plain text, PNG, and JPEG. If a selected model does not support images, reject the request with a clear message before provider invocation.
- **Credits:** Grant each new user 100 test credits. Use configurable fictional flat per-request costs, with starter tiers of 1 credit for low-cost models, 3 for mid-range models, and 5 for premium models. Keep these values in configuration, not in application logic. Do not fetch live provider prices or use token usage to calculate these simulated charges.
- **Payments:** Do not implement real payments or payment workflows. Do not add Stripe, PayMongo, taxes, chargebacks, or refunds.

At implementation time, inspect only the materials available in the workspace/course for the LiteChat proxy contract. If they do not define it, mark real-provider integration as blocked and report the exact missing information: proxy URL; authentication format and mapping of the provided credentials; request and response schema; streaming behavior; error and usage formats; supported model IDs; and image payload and model-capability rules. Application environment variable names are defined below, but they do not define the proxy's authentication contract. Do not guess any protocol details. Continue and complete the rest of the MVP using the deterministic mock provider. Revisit real-provider integration only when a verifiable contract is supplied.

### Execution Status

The available workspace contains no LiteChat proxy specification. The provided credentials alone do not define how to call the proxy. The real-provider integration is therefore blocked by these missing details: proxy URL; authentication format and credential mapping; request and response schemas; streaming behavior; error and usage formats; supported upstream model IDs; and image request format and per-model image capabilities. Continue the application with the mock provider. Do not ask the user to paste secret values into chat or repository files.

## Goal

Build **LightChat**, a classroom-simulation web app that demonstrates account-based, metered multi-provider chat. It targets OpenAI, Anthropic, and Google through the course LiteChat proxy when its contract can be verified. The full MVP must also run with a clearly labelled deterministic mock provider. Users can maintain persistent chat sessions, choose and switch configured provider/model options, send text and supported files, set system instructions, manage memory items, submit feedback, and see their test-credit balance and usage history.

The system must block a generation when the account cannot cover its configured simulated cost. It must record a test-credit grant and each generation charge in a simple auditable history.

## Scope

### In scope

- A single Django application using Python, SQLite, Django templates, and simple JavaScript where needed.
- User registration, login, logout, and a profile with display name, username, user ID, and membership date.
- Multiple persistent chats, including create, rename, revisit, archive, and delete operations.
- A configurable catalogue of supported providers/models, with model selection for a request and model/provider identity saved on each response.
- A provider abstraction and deterministic mock adapter that support the full MVP and automated tests without API credentials. Add real OpenAI, Anthropic, and Google adapters through LiteChat only if the proxy contract is available and verifiable; this integration is not a prerequisite for unrelated MVP work.
- Text prompts and bounded, allowlisted PDF, plain-text, PNG, and JPEG uploads stored in local media storage.
- Per-chat system instructions and a Global System Prompt that applies to all chats.
- User-managed Memory Items with create, edit, enable/disable, and delete controls.
- Feedback on assistant responses.
- A 100-credit initial test grant, configurable fictional per-request model costs, insufficient-credit prevention, and a user-visible balance and usage/credit history.
- Responsive, polished chat and settings UI suitable for demonstrating the full MVP.

### Explicitly out of scope

- Real payments, Stripe, PayMongo, payment methods, invoices, taxes, chargebacks, refunds, or legal/payment workflows.
- Live provider pricing as permanent application logic. The app must use its own configurable simulated per-request rate table.
- Direct calls to provider endpoints that bypass the LiteChat proxy, and guessed proxy details or model IDs.
- Production SaaS billing, subscription plans, enterprise administration, or provider key entry by end users.
- Autonomous tools, code execution, web browsing, or actions in external services.
- Automatic memory extraction, vector search, or large-document retrieval unless a later plan adds them.
- Audio, image generation, spreadsheets, or broad multimodal support. PNG/JPEG prompting is supported only when the selected model configuration declares image support.

## Proposed MVP Behavior

- Registration creates a user and one initial grant of 100 test credits. The grant appears in the usage history and cannot be duplicated by a retried registration request.
- Each configured model has one fictional, flat per-request credit cost. Starter configuration values are 1 credit for a low-cost model, 3 credits for a mid-range model, and 5 credits for a premium model. Keep these values in a configurable model catalogue, separate from charge logic. Do not use provider token counts or live provider pricing to calculate simulated charges.
- Before sending a generation, atomically verify and reserve/deduct the selected model's configured request cost. If the user does not have enough available credits, do not call the proxy. On success, record the charge. If the proxy request fails, release the test-credit reservation through a clearly labelled failed-request ledger event; this is not a payment refund workflow.
- Use integer credit arithmetic. Store the model cost/config snapshot used for each request so a later config change does not alter past history. Provider usage counts may be stored for display/debugging but do not affect the simulated per-request cost.
- The server assembles the request using the Global System Prompt, per-chat instructions, enabled memory items, conversation context, and current prompt. Keep user-controlled text separate from server authorization and never treat prompt text as a security boundary.
- The application stores canonical chat history. The user can switch provider/model for a new turn in an existing chat. Do not silently fall back to another model.
- Keep file-size limits configurable. Extract text from PDF and plain-text files. Send PNG/JPEG image content to a real provider only when both the proxy contract and selected model image support are verified; otherwise show a clear error before a real provider call. Store files in local Django media storage with authenticated, owner-scoped access. Show whether content is handled by the mock or sent through a verified LiteChat proxy.

## Data and Module Outline

Adapt entity names to the confirmed Django stack. Keep the design small and understandable; use one Django application for this classroom MVP.

- Django user/authentication storage and a profile: unique username, password hash, display name, stable user ID, membership/creation date, account state, and integer test-credit balance or a balance projection.
- `ChatSession`: owner, title, timestamps, and active/archived/deleted state.
- `Message`: session, role, typed text/file content, status, order, timestamp, and provider/model for assistant turns.
- `Attachment`: owner/session/message reference, local media path, detected type, size, and extraction status.
- `UserSettings`: Global System Prompt and update timestamp.
- `MemoryItem`: owner, content, enabled state, and timestamps.
- `ProviderModelConfig`: internal option key, target provider (`openai`, `anthropic`, or `google`), display name, optional verified upstream model ID, mock availability, image capability, and configurable flat `request_cost_credits`. Leave the upstream ID unset until verified.
- `GenerationRequest`: user/session/message, selected target provider/model option, execution mode (`mock` or verified proxy), optional proxy request state/ID and reported usage, model config snapshot, configured cost, and timestamps.
- `CreditLedgerEntry`: owner, signed integer amount, event type (`initial_test_grant`, `generation_charge`, or `failed_request_release`), generation reference, and timestamp. Ledger history supports the balance and usage display.
- `Feedback`: owner, assistant-message reference, rating, optional comment, and timestamp.

When the proxy contract is available, keep its verified URL and credentials in server-side settings/environment variables. Never include a credential in templates, JavaScript, client responses, logs, or committed configuration. Mock mode must not require proxy settings or credentials.

Keep simulated model choices, provider/model IDs, image capability flags, and 1/3/5-credit per-request costs in configuration. The shared charge code reads the configured cost; it does not contain model-specific prices.

Do not create a payment entity, payment endpoint, or payment/refund workflow for this MVP.

## Phases and Checklist

### Phase 0: Check available proxy materials and prepare the implementation branch

- [x] Fold the human answers into this plan. There are no unresolved product questions from the original plan.
- [x] Initialize the workspace as a Git repository with `main` as the primary branch.
- [x] Record Django, Python, SQLite, templates/simple JavaScript, local media, the three provider targets, mock-provider requirement, accepted file types, and 100-credit/1-3-5 per-request test-credit policy.
- [x] Record that no separate proxy documentation is currently available beyond the provided credentials. Do not guess the URL, model IDs, authentication format, or request protocol.
- [x] Inspect available workspace materials for the proxy contract. None are present. Mark only live-provider invocation `BLOCKED`; missing details are listed in the progress note below. Continue all other MVP work with the mock provider.
- [x] Record that credentials are read only from server-side environment variables. Do not print, expose, or commit credential values.
- [x] Check for `doc/canonical/`. No canonical documents are present.
- [x] Create implementation branch `feat/lightchat-mvp` from `main` before application changes.

**Exit check:** Execution is on `feat/lightchat-mvp`, secrets remain outside the repository, and the deterministic mock provider can drive the MVP. The missing proxy contract blocks real-provider invocation only; it does not block other phases.

### Phase 1: Bootstrap the Django application and core domain

- [x] Create a Django project and a single LightChat Django application. Use Django templates and static JavaScript; do not add React/Vite.
- [x] Add local run/test commands and document the Python environment setup. Use a project virtual environment and server-side environment variables; provide safe no-credential defaults for the mock demo.
- [x] Add a blank `.env.example` with the variable names above and ignore the actual root `.env` file. Never copy provided secret values into the example or other files.
- [x] Configure SQLite for persistent local classroom use, Django migrations, and local media storage under a configurable `MEDIA_ROOT`.
- [x] Add the core Django models/migrations for profile, chats, messages, settings, memories, generation requests, credit history, attachments, and feedback.
- [x] Define a configurable model catalogue for the OpenAI, Anthropic, and Google targets. Keep internal option keys, optional verified upstream IDs, image support, and fictional per-request costs separate from request/business logic. Until upstream IDs are verified, use clearly labelled mock options that do not claim to be real model IDs. Include starter 1-, 3-, and 5-credit choices.
- [x] Implement a deterministic mock provider that can serve every configured target option, return predictable responses, and simulate success and failure without proxy settings or credentials. Identify mock responses as mock in the UI and stored request data.
- [x] Add shared form/request validation, user ownership checks, clear error handling, and minimal responsive base templates.

**Verification:** `.venv/bin/python manage.py check`, migrations, and `.venv/bin/python manage.py test` pass. The app uses SQLite and local media. Tests load all three target-provider options and mock them without any proxy URL or credentials. Changing a model's configured request cost changes later generation charges without changing charge logic.

### Phase 2: Django accounts, profile, and test-credit ledger

- [x] Use Django authentication for registration, login, logout, and protected views. Use Django password hashing; never store plaintext passwords.
- [x] Enforce unique usernames and validate display-name/username changes.
- [x] Create profile data with display name, stable user ID, and membership date.
- [x] Grant exactly 100 test credits when a new account is created. Record one `initial_test_grant` ledger entry and make grant creation idempotent.
- [x] Add an integer balance and append-only credit history for grants, generation charges, and technical failed-request releases. Keep balance changes and ledger entries in one database transaction.
- [x] Use an atomic conditional balance update or another SQLite-safe transaction pattern to prevent concurrent requests from spending more credits than the user has.
- [x] Add Settings UI for profile information, remaining credits, and a simple usage/credit history.
- [x] Do not add payment setup, payment routes, billing SDKs, or purchasable credits.

**Verification:** Django tests cover registration/login/logout, duplicate username rejection, profile values, the 100-credit grant exactly once, account isolation, balance/history updates, insufficient balance, duplicate request replay, and technical failure release. Confirm that no provider credential or password appears in templates, client responses, or logs.

### Phase 3: LiteChat proxy, provider/model selection, and per-request credits

- [x] Implement the internal provider interface independently from the LiteChat proxy transport.
- [BLOCKED] Real-provider invocation: no verifiable proxy URL, authentication/credential mapping, request/response schema, streaming behavior, error/usage formats, upstream model IDs, or image contract is available. Do not guess these details. Continue all other Phase 3 tasks and later phases through the mock provider.
- [x] Add mock provider/model mappings for OpenAI, Anthropic, and Google targets. Keep upstream IDs unset because none are verified.
- [x] Keep the deterministic mock provider available to the app and tests without proxy settings or credentials. Do not label mock output as a real provider response.
- [x] Add model selection to the chat composer. Show the target provider/model option, its image capability, and whether the current response path is mock or real.
- [x] Build request context from the selected model, Global System Prompt, per-chat instructions, enabled memories, supported chat history, current prompt, and any attached supported content.
- [x] Persist user and assistant messages, provider/model selection, response status, optional provider usage, configured per-request cost, and a config snapshot.
- [x] Read one integer `request_cost_credits` from the selected model configuration. Charge one fixed cost per successful generation; do not derive charges from token counts or current provider pricing.
- [x] Atomically reject and avoid calling a provider when the user has fewer credits than the selected model's configured cost. Record the reservation charge and generation in a transaction. On failure, release test credits through a separate ledger entry.
- [x] Add duplicate-submit protection with client request IDs, durable request state, and replay/recovery for pending mock requests.
- [x] If an attached image is submitted to a model without image support, return a clear user-facing error before provider invocation. Mock image options are labelled as mock.
- [x] Allow the user to choose a different model for a later turn in the same chat. Do not silently change the selected model on an error.

**Verification:** Complete all generation tests without proxy settings or credentials using the mock provider. Django tests cover configured 1/3/5 costs, no token-based charge changes, configuration changes, insufficient credits preventing provider invocation, failure releases, and request replay/recovery. Real proxy tests are blocked by the missing contract; this does not block the MVP.

### Phase 4: Persistent chat management and settings instructions/memory

- [x] Add chat list and create-chat behavior.
- [x] Support rename, revisit, archive, and delete for a user-owned session. Delete its messages and local attachments.
- [x] Persist message ordering, request status, and assistant target provider/model identity.
- [x] Add a Global System Prompt editor and save behavior. Apply it on requests in every chat.
- [x] Add per-chat system instructions. Include both the Global System Prompt and chat-specific instructions in every request, with clear separation and a consistent order.
- [x] Add Memory Item create, list, edit, enable/disable, and delete controls in Settings.
- [x] Include only enabled, owner-scoped memories in generation context. Exclude disabled/deleted items.
- [x] Add context-size safeguards for recent messages, memory items, and extracted file text.

**Verification:** Django tests cover chat create/rename/revisit/archive/delete, stored messages, provider-option switching, global and per-chat instruction context, memory CRUD/inclusion/disable/delete, and user isolation.

### Phase 5: Bounded file prompting

- [x] Implement configurable upload-size validation for PDF, plain text, PNG, and JPEG. Reject unsupported formats and malformed/oversized files with a clear message.
- [x] Store files in local Django media storage with owner-scoped authenticated access. Do not expose uploaded media through unrestricted static URLs.
- [x] Extract bounded text from PDF and plain-text files and record extraction status/errors.
- [x] Allow the user to attach supported files to a chat prompt and persist attachment/message relationships.
- [x] In mock mode, exercise PNG/JPEG attachments through deterministic mock behavior. Real image calls remain blocked until proxy/model capability details are verified.
- [x] Show attached files and explain whether content is handled by the mock provider or sent through a verified LiteChat proxy integration.
- [x] Ensure chat/account deletion removes associated local media and extracted text, including account deletion.

**Verification:** Django tests cover PDF, plain text, PNG, JPEG, unsupported formats, configurable limits, oversized files rejected before body reads, malformed files, extraction failures, persistence/revisit, unauthorized downloads, and media deletion.

### Phase 6: Feedback, usage history, and responsive UI completion

- [x] Add response feedback controls with rating and optional text comment.
- [x] Associate feedback with the authenticated user and the correct assistant message. Do not send feedback to a provider.
- [x] Complete Settings UI for profile, Global System Prompt, Memory Items, remaining credits, and credit/usage history.
- [x] Show each usage entry's timestamp, chat/model, fixed simulated credit cost, and event type. Do not present token usage as the basis for the simulated charge.
- [x] Ensure model/provider changes are visible in the conversation and model picker.
- [x] Add empty, loading, mock, insufficient-credit, provider-blocked, upload-error, and no-credentials demo states.
- [x] Add responsive CSS layouts and keyboard-accessible native form controls for chat, model selection, file upload, feedback, and Settings.

**Verification:** Django client tests exercise Settings controls, feedback, model switching, usage history, and rendered chat controls. `node --check` passes. CSS includes mobile and desktop layouts; no browser automation is available for visual verification.

### Phase 7: Final integration, security checks, and handoff

- [x] Run `.venv/bin/python manage.py check`, migration checks, `.venv/bin/python manage.py test`, `node --check lightchat/static/lightchat/app.js`, and the classroom flow test.
- [x] Run a mock-backed classroom flow without proxy settings: register, receive 100 test credits, create chats, select mock target options, prompt with text and supported files, switch models, revisit/rename/manage chats, update global instructions, create/disable/delete memories, submit feedback, and inspect credit history.
- [BLOCKED] Real-provider smoke test. Report the missing proxy URL; authentication format and credential mapping; request/response schemas; streaming behavior; error/usage formats; upstream model IDs; and image payload/capability rules. Do not block other acceptance checks.
- [x] Confirm configured 1-, 3-, and 5-credit request costs apply per successful generation and are recorded on each request independently from provider prices or token counts.
- [x] Confirm an insufficient-credit request is rejected before mock or real-provider invocation.
- [x] Confirm mock image prompts use deterministic behavior and unsupported image/model combinations fail before provider invocation.
- [x] Check ownership boundaries, environment-only credentials, safe text rendering, local media access/deletion, upload limits, and absence of payment processing/live-price logic.
- [x] Review intended changes. Suggested implementation commit: `feat: build LightChat metered multi-provider MVP`.
- [ ] Commit the implementation branch with the scoped Conventional Commit.
- [ ] Merge the implementation branch into `main` and rerun checks after the merge.
- [ ] Update this checklist as rendezvous tasks complete. Do not sync wiki docs during execution or rendezvous.

**Rendezvous after execution:** Merge the implementation branch back to `main` unless a clear repository constraint prevents it. Run the appropriate test/build/smoke checks again after the merge. Report the merge and verification results.

**Documentation sync is separate:** Do not update living docs during implementation or rendezvous. After the implementation is merged, perform `sync docs` as its own stage, update supported facts in `doc/wiki/`, and record noteworthy behavior in `doc/wiki/footguns/`. Treat `doc/canonical/` as authoritative.

## Acceptance Criteria

- A user can register, log in, and see profile details including display name, username, user ID, and membership date.
- A new user receives exactly 100 test credits recorded once in the usage history.
- A user can create multiple chats, revisit them after reload, rename them, archive them, and delete them.
- A user can select mock-backed options for the OpenAI, Anthropic, and Google targets and can select a different option for a later turn in the same chat. Real proxy calls remain disabled because their contract and model IDs are not verified.
- The actual provider/model identity is visible and persisted with every assistant response.
- A user can send text, provide per-chat instructions, and upload PDF, plain text, PNG, and JPEG within configurable limits. Image requests to models without image support fail clearly before provider invocation.
- The mock provider supports the complete MVP without proxy configuration or credentials and is clearly identified as mock. If a verified proxy contract is available, real requests use that contract and server-side credentials; otherwise real-provider integration is reported as blocked with exact missing details while the rest of the MVP is completed.
- The Global System Prompt is applied to requests in all chats. Enabled memories are included, disabled memories are excluded, and users can create/edit/toggle/delete memory items.
- A user can submit feedback for an assistant response.
- Configured fictional per-request costs (starter examples: 1, 3, and 5 credits) cause different models to consume different amounts. The costs do not depend on token counts or current provider prices.
- An insufficient balance prevents a mock or proxy/provider call. Successful requests create a traceable credit charge; technical request failures release the test-credit reservation; usage/credit history shows grants, charges, and releases.
- User data and locally stored uploaded files are isolated by account. Provider credentials remain server-side.
- No real payment processing or payment-related workflow exists.
- The project runs and passes its automated checks and mock-backed classroom flow test. Real-provider invocation remains explicitly blocked until the missing contract details are supplied.

## Execution Notes

- Follow `AGENTS.md`: `main` is the primary branch. Execute this existing plan on a separate branch created from `main`, update this checklist as work progresses, and rendezvous by merging to `main` and verifying after merge.
- Keep the implementation focused enough for one `feat:` Conventional Commit when possible. Do not commit unrelated work.
- Use `TODO.md` as the editable general todo list during implementation if a general todo list is needed; this plan remains the feature-specific task board.
- Do not perform documentation sync until explicitly requested after rendezvous.
- The original plan is committed on `main`. Execution checklist updates are included with the implementation branch and will merge at rendezvous.
