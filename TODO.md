# LightChat MVP TODO

Plan: `doc/plan/1790659197_lightchat-mvp.md`
Branch: `feat/lightchat-mvp`

## Preflight

- [x] Re-read repository instructions and the committed LightChat plan.
- [x] Confirm the workspace has no application scaffold or canonical documentation.
- [x] Confirm no LiteChat proxy URL/protocol/model documentation is available. Keep real-provider invocation blocked; do not guess.
- [x] Create the implementation branch from `main` before application code changes.
- [x] Build the complete MVP around the deterministic mock provider.
- [x] Record the exact missing proxy contract items in the plan. Real-provider invocation remains blocked.

## Implementation

- [x] Bootstrap a Django project and one LightChat Django app with SQLite and local media storage.
- [x] Add a project virtual environment and load local environment values from an ignored root `.env` file.
- [x] Add Django authentication, profile details, and a one-time 100-credit grant.
- [x] Add configurable provider/model options and a deterministic mock adapter for OpenAI, Anthropic, and Google targets.
- [x] Add persistent chat sessions, model switching, Global System Prompt, per-chat instructions, and Memory Items.
- [x] Add configurable flat per-request test-credit costs (starter values 1/3/5), insufficient-credit blocking, and usage history.
- [x] Add PDF/TXT extraction and PNG/JPEG mock prompting with configurable size limits and capability checks.
- [x] Add feedback, Settings, responsive Django templates, and safe local media access.
- [x] Add tests for accounts, persistence, model selection, mock generation, credit accounting, uploads, prompts, memories, and feedback.
- [x] Keep all real proxy calls disabled because no verifiable contract is available.

## Verification and Handoff

- [x] Run Django checks, migrations, tests, and the mock-backed classroom flow test.
- [x] Review the diff and commit the implementation as a Conventional Commit (`2496c3c`).
- [x] Fast-forward merge the implementation branch into `main` and rerun checks after the merge.
- Living documentation sync remains a separate stage and was not performed.

## CodeRange Host Fix

Plan: `doc/plan/1790664694_code-range-allowed-hosts.md`
Branch: `fix/code-range-allowed-hosts`

- [x] Study Django `ALLOWED_HOSTS` behavior and confirm the current fallback allows localhost only.
- [x] Confirm no local `.env` file is present. Do not read or alter credential values.
- [x] Create an implementation branch from `main`.
- [x] Add debug-only wildcard host support through `DJANGO_ALLOWED_HOSTS`.
- [x] Test a dynamically named forwarded host and reject wildcards outside debug mode.
- [x] Run Django checks and all tests (30 tests pass).
- [x] Commit the fix as `1cd75f1`.
- [x] Fast-forward merge to `main` and verify after merge.
- [x] Sync living docs in `doc/wiki/` separately after rendezvous.

## Forwarded Static Assets

Plan: `doc/plan/1790666703_forwarded-static-assets.md`
Branch: `fix/forwarded-static-assets`

- [x] Confirm static URL output is root-prefixed and missing the forwarded script prefix.
- [x] Create an implementation branch from `main`.
- [x] Add request-prefix-aware URLs for the CSS and JavaScript assets.
- [x] Verify both assets through forwarded and local paths and verify login-page links.
- [ ] Commit, rendezvous to `main`, sync living docs separately, and verify final state.
