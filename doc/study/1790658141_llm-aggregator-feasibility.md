# Multi-Provider LLM Chat Application Feasibility Study

- **Study date:** 2026-09-29
- **Unix timestamp:** `1790658141`
- **Purpose:** Assess the feasibility, architecture, data, billing, integration, and risk areas for a consumer application that offers metered access to LLMs from multiple providers.
- **Status:** Research only. This document does not define an implementation plan or implement the application.

## Executive Summary

The application is feasible with current commercial LLM APIs. A small team can build a useful first release without training or hosting foundation models. The application can call provider APIs using centrally managed provider accounts, store chats in its own database, and charge users through an application-managed credit ledger.

The chat interface is not the main risk. The main risks are:

- Correctly reserving and settling user credits when provider usage, provider prices, and requests differ.
- Maintaining a reliable model catalogue as providers change prices, model identifiers, limits, features, and availability.
- Protecting prompts, files, memories, and chat histories across the application and each external provider.
- Avoiding losses caused by abuse, unexpectedly long prompts, costly models, retries, and concurrent requests.
- Explaining to users that a "credit" is an application billing unit, not a fixed amount of tokens or equivalent model quality.

The recommended first release is a modular application with a server-side provider layer, a relational database, object storage for files, and an append-only credit ledger. The application should own canonical chat history. It should begin with a narrow, explicit set of text models from two providers, expose per-request cost information, and keep provider-specific capabilities visible. Add more models and modalities after metering and reconciliation are proven.

## Scope and Assumptions

This study interprets "metered, a-la-carte access" as follows:

- The application pays providers through its own provider accounts and API keys.
- The user pays the application for credits or usage.
- The application selects which provider model receives each request.
- Users do not need a separate consumer subscription for every LLM provider.

This is different from a bring-your-own-provider-key product. It makes the product simpler for users, but it transfers provider spend, credit risk, support, and compliance duties to the application operator.

The stated support for complex, multi-step tasks means users can ask a model to reason through a multi-part request. It does not, by itself, mean the model can run code, browse websites, or take actions in other services. Tool execution is a separate product and security scope.

No existing application stack, deployment platform, customer jurisdiction, provider contract, or pricing policy was available for this study. Those choices need review during planning.

## Feasibility by Capability

| Capability | Feasibility | Main condition |
| --- | --- | --- |
| Accounts and profile settings | High | Use a maintained authentication service or library, and enforce account ownership on every data operation. |
| Chat sessions and history | High | Store canonical messages and file references in the application, not only in provider conversation state. |
| Model selection and switching | High | Normalize common text-chat behavior, but publish model-specific capabilities and retain provider/model identifiers per turn. |
| Global system prompt | High | Apply it server-side to each new model request. Treat it as user content, not as a secret or security boundary. |
| User-managed memory items | High | Start with explicit user-created, editable items. Make inclusion and deletion understandable. |
| File uploads | High for a bounded set of formats | Validate, scan, parse, limit, and store files securely. File understanding can add token, OCR, storage, and provider-specific costs. |
| Feedback | High | Store the rating and optional comment. Tell users whether the related prompt and response are included in feedback. |
| Credits and usage history | High, with material financial risk | Use an append-only ledger, pre-request reservation, idempotency, and provider-bill reconciliation. |
| Several provider integrations | Medium to high | Each provider has different request formats, usage details, features, rate limits, and data terms. Maintain adapters and a capability catalogue. |
| Autonomous tool-using agents | Medium, but outside a basic chat release | Requires permission controls, sandboxing, step limits, cost caps, action confirmation, and prompt-injection defenses. |

## Recommended System Shape

Use a modular monolith for an initial product. It keeps billing and conversation operations in one deployable service while still separating their responsibilities in code. Microservices are not needed to prove this product.

Main components:

1. **Web client:** Account, chat, model picker, file controls, usage display, settings, and feedback.
2. **Application API:** Authenticated operations for profiles, chats, prompts, memories, files, feedback, and billing.
3. **Conversation orchestrator:** Builds a request from the selected model, chat history, current user turn, global prompt, optional chat instructions, memory items, and allowed file content.
4. **Provider adapters:** Translate the application's supported request format into provider-specific requests. Normalize streams, errors, completion status, and usage data into an internal response format.
5. **Model and price catalogue:** Defines enabled provider/model pairs, feature support, limits, model lifecycle, and versioned cost rates.
6. **Relational database:** Stores users, chats, messages, settings, usage requests, credit ledger entries, and billing records.
7. **Object storage:** Stores uploaded files and derived artifacts. Objects must be private and scoped to their owner.
8. **Payment integration:** Sells credit packs or handles other chosen payment events. Payment webhooks must be authenticated and idempotent.
9. **Operational services:** Secrets management, rate limits, monitoring, audit events, background file scanning, and usage reconciliation.

Use a server-side streaming transport, such as Server-Sent Events, to deliver generated text. The server must keep control of provider credentials, request limits, and billing state. Never send provider API keys to the browser.

The app should own the conversation source of truth. Provider-hosted conversation IDs can be useful in some integrations, but should not be required to reopen, export, delete, or switch a chat to another provider.

## Suggested Data Model

These are logical entities, not a required database schema.

| Entity | Important fields and purpose |
| --- | --- |
| `User` | Internal ID, authentication subject, account state, created date, and membership date. Keep public username and display name distinct from the internal user ID. |
| `UserSettings` | User ID, global system prompt, prompt update time, privacy and retention choices where supported. |
| `MemoryItem` | User ID, content, optional category, created/updated time, active/deleted state, and optionally whether it is included by default. Each item must be easy to inspect, edit, and remove. |
| `ChatSession` | User ID, title, created/updated time, archived/deleted state, and optional default provider/model. |
| `Message` | Session ID, role, ordered position, content blocks, status, created time, and provider/model identifiers for assistant turns. Store tool calls and results as typed blocks if tools are later supported. |
| `Attachment` | Owner and message/session IDs, private object key, original filename, detected media type, byte size, scan/parse status, retention state, and safe extracted-text reference. |
| `Provider` and `Model` | Provider name, external model ID, display name, enabled state, supported inputs and features, context/output limits, and lifecycle status. Do not assume an external model name is permanent. |
| `PriceVersion` | Provider/model ID, effective time range, input/output/cached-token rates, modality/tool charges, currency, and source or administrative audit information. Keep old versions for past usage calculations. |
| `GenerationRequest` | User, chat, triggering message, idempotency key, provider/model, request state, rate version, reserved credits, reported usage, calculated provider cost, user charge, and timestamps. |
| `CreditAccount` | User ID and an optional cached available balance. This is a performance view, not the sole source of truth. |
| `CreditLedgerEntry` | User ID, signed integer credit amount, event type, request or payment reference, idempotency key, timestamp, and audit metadata. Entries should be append-only. |
| `Payment` | User, payment processor reference, amount, currency, state, and related credit grant/refund. Avoid storing card data. |
| `Feedback` | User, assistant message, rating, optional comment, timestamp, and an explicit record of any content shared with the feedback provider. |

Use integer units for money and credits. Do not use floating-point arithmetic for charges. A cached balance can make the settings page fast, but ledger entries must support an audit and reconstruction of that balance.

## Request and Credit Lifecycle

An individual generation request should have a traceable lifecycle:

1. Authenticate the user and confirm that the session, messages, and attachments belong to that user.
2. Resolve the selected provider/model from the enabled catalogue. Check its limits and current price version.
3. Assemble only the context needed for this turn. Estimate likely input and output cost. Show an estimate or a warning for unusually costly requests.
4. In a database transaction, reserve enough credits for the configured maximum request cost. Reject the request if funds are not available. Use an idempotency key so a client retry does not create a second charge or provider request.
5. Send the request through the provider adapter. Stream the response, persist its state, and set a maximum output-token or cost limit where the provider supports it.
6. On completion, read the provider-reported usage categories. Calculate the user charge using the price version captured at request start. Record provider cost and user charge separately.
7. Settle the reservation: debit the final amount and release unused reserved credits. Record failures and partial usage according to a clear user policy.
8. Reconcile application usage against provider billing reports. Raise alerts for missing usage, unexplained differences, and negative-margin model traffic.

Do not blindly retry a timed-out generation. The provider may have completed and billed the first request even when the application did not receive its response. Keep an `unknown` or `reconciling` state when the result is uncertain, and use provider idempotency features where available.

If provider usage data is absent or delayed, use a disclosed fallback estimate and mark it as estimated. Reconcile later. Define whether the application absorbs uncertainty or applies a bounded later adjustment; unexpected retroactive charges are likely to damage trust.

## Credits, Usage, and Provider Cost

Provider cost is not a single price per message. A basic text request can have separate input and output rates. Other chargeable categories may include cached input, cache creation, image input/output, audio duration, web-search calls, code execution, storage, or other tools. Features and rate categories differ by provider and model.

A simplified token cost formula is:

```text
provider_cost =
  input_tokens * input_rate
  + cached_input_tokens * cached_input_rate
  + output_tokens * output_rate
  + other_billable_usage
```

The rates are normally expressed per million tokens, so the calculated amount must be divided by one million. Real requests can have more categories and special pricing rules. Use the provider's returned usage breakdown as the best available source for settlement, not a character-count estimate from the browser.

Prices can differ sharply even within one provider. At the time of research, OpenAI's published standard table listed GPT-5.6 Luna at USD $0.20 per million input tokens and $1.20 per million output tokens, while GPT-5.6 Sol was listed at USD $4.00 and $20.00. Anthropic's published table listed Claude Haiku 4.5 at USD $1 and $5 per million input/output tokens and Claude Opus 5.5 at USD $4 and $20. These examples show why a common "one message equals one credit" rate is not viable. They are snapshots, not a pricing promise, and they do not imply that the models have equivalent quality or capabilities.

Application pricing must account for:

- Provider charges, including tool and modality costs.
- Payment processing, taxes, refunds, chargebacks, and fraud losses.
- Hosting, storage, support, and operational costs.
- Provider price changes, discounts, minimums, and billing adjustments.
- The application's margin and the cost of failed or abusive requests.

The product can display credits while internally calculating precise cost units. Explain the credit conversion and show per-request usage in understandable units. Consider a user-visible estimate before a request and an itemized usage record after it. "Remaining credits" without a definition is not enough for informed use.

Choose a credit policy before implementation. The policy needs to define credit value, purchase sizes, promotional credits, expiration, refunds, chargebacks, low-balance behavior, and whether a generation can incur a final charge after a connection failure. These are product and legal decisions as well as engineering requirements.

## Provider Integration and Model Differences

Build one internal interface for the subset of behavior the application intends to support. Do not pretend that all provider features are interchangeable. A provider adapter should normalize:

- Text and supported content-block formats.
- Streaming chunks and terminal completion/error events.
- Usage categories and provider request identifiers.
- Context limits, output limits, and capability metadata.
- Retryable errors, rate limits, and temporary unavailability.
- Supported tools, structured output, image/file inputs, and other optional features.

Maintain a capability matrix in the model catalogue. The user should be able to see relevant differences, such as text-only versus image support, context size, availability, and approximate cost. Do not silently switch a request to another model if the selected one fails. Offer an explicit user choice or a clearly disclosed fallback.

When the user switches models in an existing chat, retain the application's canonical conversation. Convert supported content to the new provider's request format and omit or clearly represent unsupported content. Do not assume that system roles, tool calls, structured output, image blocks, tokenization, or safety behavior match across providers. Save the actual model/provider for each assistant turn so old responses remain understandable.

Model IDs and prices are operational data. Providers can add, retire, rename, or alias models, and an alias can change its underlying model. Store the requested identifier and the resolved identifier when available. Monitor provider lifecycle notices and disable models safely when needed.

Direct provider integration gives more control over model choice, feature use, pricing, and data terms, but it requires several adapters and more operational work. An aggregator API can reduce initial integration effort, but adds another data processor, a possible markup, a dependency, and differences in feature availability or usage detail. A provider interface can preserve the option to use either approach, but the first release should choose a primary path rather than build a complex routing layer prematurely.

## Chat Persistence and Context Assembly

Persist chats in the application database. A user should be able to create, rename, revisit, archive, and delete sessions without depending on an external provider's conversation retention policy.

Store each message as typed content, not only as a single plain-text column. Typed blocks support text, file references, images, tool calls, and provider metadata. Keep the raw provider response only where it is needed for audit or troubleshooting, and apply an explicit retention policy because raw requests may contain sensitive information.

The model receives a constructed context, not necessarily the complete stored chat. Re-sending a growing history can make later turns slower and more expensive. Context assembly should select recent or otherwise relevant history, respect the model's context limit, and use a disclosed truncation or summarization policy. Summaries should be identifiable as summaries, not presented as exact original messages.

For each generation, define and test the order of instructions. A reasonable application policy is global user instructions, chat-specific instructions, selected memory items, and conversation content, mapped to the provider's supported request fields. Do not place user-controlled message text into a privileged system role where it can be confused with application policy. Do not promise that a system prompt is secret; models can expose or disregard instructions.

## Global Prompt and Memory Items

The global system prompt can be stored as a setting and included in future requests. A user can change it at any time. A generation record may need to retain a version or snapshot of the effective instructions for debugging and cost reconstruction, subject to a documented retention policy.

Memory items are persistent personal data, not harmless prompt decoration. A safe first release should make users create, view, edit, disable, and delete items themselves. Show when memory is used, and let users opt out of including it in a chat. If the product later adds automatic memory extraction, require user review or provide clear controls and a strong deletion path.

Treat both the global prompt and memory as untrusted, user-controlled content. They can contain malicious instructions or sensitive data. They must not grant application permissions or bypass server-side authorization.

## File Uploads

File upload support is feasible, but "upload a file" is not one operation. It may mean storing a file, extracting text, running OCR, converting pages to images, or passing a provider-specific file reference. Each path has different cost and retention behavior.

For an initial release, support a small allowlist of formats and size/page limits. The upload flow should:

- Check authentication, ownership, file size, extension, and detected media type.
- Store files outside the web root in private object storage.
- Scan files and parse them in a restricted process.
- Reject malformed files, executable content, and decompression bombs.
- Keep original files and extracted text under an explicit retention and deletion policy.
- Use private, short-lived download links where links are necessary.
- Record which attachment was sent to which provider and model.
- Explain that an uploaded file may be sent to an external provider for processing.

Extracted text and image tokens can be costly. Do not send every page of every uploaded file on every turn without a deliberate context and cost policy. Retrieval over chunks can help with large files, but it adds an indexing pipeline, storage, access-control rules, and embedding costs.

## Security and Privacy

The service will handle account data, chat transcripts, personal memories, uploaded files, payment events, and provider API keys. Treat this as sensitive user data.

### Application security

- Keep provider keys in a secrets manager or equivalent server-side secret store. Rotate them and restrict their scope.
- Enforce ownership checks on every read, update, download, and delete operation. Unpredictable IDs do not replace authorization checks.
- Use secure authentication sessions, CSRF protections where applicable, rate limits, and abuse controls.
- Validate uploads by content and parse them in isolation. Do not trust filenames or browser-provided MIME types.
- Render model output as untrusted content. Sanitize HTML and markdown links; prevent script execution and unsafe URL handling.
- Validate payment webhooks and make webhook processing idempotent.
- Redact prompts, responses, files, secrets, and personal data from ordinary logs. Limit staff access and audit administrative access.
- Set per-user request, token, upload, and spending limits to reduce denial-of-wallet and unbounded-consumption risk.

### LLM-specific security

Prompt injection can arrive in user text, retrieved documents, and uploaded files. A model response must not be treated as authorization to perform an action. If tools are later introduced, allowlist tools, constrain their inputs, isolate code execution, cap steps and spend, and ask the user before external side effects.

Other relevant risks include sensitive information disclosure, unsafe output rendering, excessive agency, prompt leakage, and unbounded consumption. A system prompt is not a substitute for access control or data isolation.

### Provider data handling

Sending a message to an LLM provider sends user data outside the application. Provider retention and feature behavior differ. For example, OpenAI's API data-controls documentation says API data is not used to train or improve models by default, but describes default abuse-monitoring retention of up to 30 days and separate application-state retention for some endpoints and features. Anthropic's commercial API retention documentation describes deletion of ordinary API inputs and outputs within 30 days, with exceptions. Those statements do not make the two providers' terms identical, and they can change.

Before launch, review the contracts, data processing terms, retention controls, supported regions, subprocessors, and feature-specific behavior for every enabled provider. Give users a clear notice about external processing. Avoid absolute privacy promises unless the exact provider configuration and contract support them. Decide how account deletion, chat deletion, file deletion, backups, provider-side state, and legal retention work together.

This study is not legal advice. The operator must assess applicable privacy, consumer, payment, tax, and data-residency rules for its target markets.

## Major Implementation Challenges

1. **Billing correctness:** Reservations, concurrent requests, streamed partial responses, duplicate webhooks, retries, and uncertain provider outcomes all affect the balance.
2. **Cost estimation:** The application cannot know exact output usage in advance. Tokenizers differ, and tools, caching, images, and audio add non-token charges.
3. **Price maintenance:** Rates need effective dates and audit history. A pricing change during a request must not change the rate used to settle that request.
4. **Provider differences:** A shared interface can cover common text chat, but not all provider capabilities or semantics.
5. **Abuse and profitability:** Attackers or accidental loops can consume provider spend before the application collects payment. Apply spend caps, velocity limits, and model-specific restrictions.
6. **Long conversations:** Persisting the full transcript is straightforward; deciding which parts fit into a provider request is not. Repeatedly resending a large history increases cost.
7. **Privacy deletion:** The application must track data in messages, attachment storage, derived text, logs, backups, and optional provider-side features.
8. **Provider availability and quotas:** Rate limits and outages are separate for each provider and shared across the application's users. The application needs backpressure and clear errors.
9. **User trust:** Users need clear cost estimates, final usage, model identity, credit rules, and explanations of data sharing.
10. **Quality expectations:** Model choice changes behavior and quality. Model labels alone do not establish that two models are comparable for a task.

## Important Tradeoffs

| Decision | Option A | Option B | Practical guidance |
| --- | --- | --- | --- |
| User billing display | USD-style exact usage | Abstract application credits | Credits support prepaid use, but publish conversion rules and show per-request detail. Keep precise internal accounting either way. |
| Charge timing | Charge only after completion | Reserve before calling the provider | Reserve before calling to prevent concurrent overspend, then settle and release unused credits. State how partial failures are charged. |
| Conversation state | Provider-hosted state | Application-owned canonical history | Application-owned history improves portability, deletion, and model switching. It makes context assembly the application's responsibility. |
| Provider access | Direct APIs | Aggregator API | Direct APIs give control and feature access; aggregators can speed up integration but add a dependency and data path. |
| Memory behavior | Manually managed items | Automatically inferred memories | Manual items are easier to explain and govern. Automatic inference adds privacy, accuracy, and consent risks. |
| File support | Narrow format/size allowlist | General file and media support | Start narrow. General support increases parser, moderation, storage, and cost complexity. |
| Model fallback | Silent automatic fallback | Ask or disclose before switching | Do not silently use a different model when the user selected one. |
| Agent tools | Chat-only reasoning | Tool execution and autonomous actions | Keep tools outside the initial scope unless they are a firm product requirement. They need separate safety and spend controls. |

## Suggested Release Scope

An initial release should prove user value and billing correctness before it expands into a broad AI platform.

**Core release:**

- Account registration, login, profile, and membership date.
- Create, rename, revisit, archive, and delete chat sessions.
- Select from a small, explicit model catalogue from at least two providers.
- Text chat with streaming, provider/model labels, and usage details.
- Global system prompt and manually managed memory items.
- Credit purchase or another defined funding method, credit balance, append-only ledger, and request settlement.
- Bounded file uploads, starting with selected document types and explicit size limits.
- Feedback tied to a response, with a clear notice about what the feedback contains.
- Per-user spending limits, rate limits, audit events, and provider usage reconciliation.

**Later scope unless required for launch:**

- Autonomous code execution, browsing, or external actions.
- Automatic memory extraction.
- Large-file retrieval and vector search.
- Audio, image generation, real-time voice, or complex multimodal workflows.
- Silent model routing or fallback.
- Many model families before pricing and operations are stable.

"Complex multi-step tasks" can be supported in the core release as model-generated analysis and writing. If it must mean the model can perform actions or use tools, add an explicit tool-execution scope with user approvals and hard cost limits.

## Open Product Decisions for Planning

- Which initial providers, models, and model capabilities are required?
- Will users buy prepaid credits, pay after use, or use another billing approach?
- What monetary value does one credit represent? Do credits expire, and how are promotional credits consumed?
- What margin or pricing rule covers provider costs and non-provider overhead?
- What is the maximum request spend, output size, session spend, and monthly spend per user?
- Which countries and currencies are in scope? Which privacy, tax, payment, and data-residency requirements apply?
- Which file formats and limits are needed at launch? Are images, OCR, and large-document retrieval required?
- Is tool execution required, or is multi-step model reasoning enough for the first release?
- What chat, file, memory, usage, and backup retention/deletion policy will users receive?
- Will users see a price estimate before every generation, and how will uncertain or partial provider charges be handled?

## Conclusion

The product is technically feasible and can be built incrementally. It is best understood as a billing, privacy, and provider-orchestration product with a chat interface, not as a thin wrapper around several APIs.

The project should proceed only after the credit policy, provider set, data-handling commitments, target markets, and definition of multi-step tasks are clear. The most important early proof is a single end-to-end request that reserves credits, streams a response, records provider-reported usage, settles the ledger idempotently, and reconciles with provider billing. That proof should precede a large model catalogue or autonomous tools.

## Sources

Provider pricing and privacy terms change. The following sources were consulted on 2026-09-29. The linked pricing pages are the authoritative locations to re-check during planning and before launch.

- OpenAI API pricing: <https://developers.openai.com/api/docs/pricing>
- OpenAI API data controls and retention: <https://platform.openai.com/docs/guides/your-data>
- Anthropic Claude API pricing: <https://docs.anthropic.com/en/docs/about-claude/pricing>
- Anthropic commercial API data retention: <https://privacy.anthropic.com/en/articles/7996866-how-long-do-you-store-my-data>
- Stripe usage-based billing event recording: <https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage>
- OWASP GenAI Security Project, 2025 Top 10 risks: <https://genai.owasp.org/llm-top-10/>
