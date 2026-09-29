# CodeRange Host Configuration Plan

- **Status:** Local host configuration and verification are complete. Commit `1cd75f1` is on `fix/code-range-allowed-hosts`; rendezvous is pending.
- **Created:** 2026-09-29 06:51:34 UTC
- **Study:** `doc/study/1790664555_code-range-allowed-hosts.md`
- **Scope:** Fix the local CodeRange `DisallowedHost` error without adding a session-specific hostname.

## Objective

Allow the Django classroom app to accept CodeRange's dynamically forwarded host through `DJANGO_ALLOWED_HOSTS`. Keep normal production host validation strict. Do not guess or add a CodeRange domain or a session URL.

## Decisions

- In local debug mode, include the `*` host entry in the default `DJANGO_ALLOWED_HOSTS` value and in `.env.example`. This supports changing CodeRange subdomains without a per-session edit.
- Use the existing `DJANGO_ALLOWED_HOSTS` environment variable. Keep localhost entries.
- Reject `*` when `DJANGO_DEBUG` is false. This prevents the local wildcard setting from silently becoming a production setting.
- Do not enable `USE_X_FORWARDED_HOST`. The current issue does not establish that the proxy sends `X-Forwarded-Host` or that the app should trust it.
- Do not read or change any provider credentials or other values in `.env`. The workspace currently has no `.env` file.

## Implementation Task Board

### Phase 0: Prepare

- [x] Confirm `main` is clean and create `fix/code-range-allowed-hosts` from `main`.
- [x] Confirm there is no local `.env` file. Do not inspect or change provider credentials.

### Phase 1: Configure local host validation

- [x] Add a small parser for `DJANGO_ALLOWED_HOSTS` in `lightchat_site/settings.py`.
- [x] When the variable is absent, use `127.0.0.1,localhost,*` only when debug mode is on. Keep the fallback strict when debug mode is off.
- [x] Reject `*` when `DJANGO_DEBUG=false` with a clear configuration error.
- [x] Update `.env.example` to include `*` with the localhost names. Do not add any forwarded or session-specific host.
- [x] Update the local setup documentation. State that wildcard hosts are only for CodeRange/local debug use.

### Phase 2: Verify behavior

- [x] Add a Django test that sends a request with a dynamically generated CodeRange-style forwarded host and confirms it is not rejected as `DisallowedHost` under the local configuration.
- [x] Add a settings test that confirms wildcard configuration is rejected when debug mode is off.
- [x] Confirm explicit host entries still parse and work.
- [x] Run `.venv/bin/python manage.py check` and `.venv/bin/python manage.py test`.
- [x] Confirm no `.env` values were read, printed, or changed. Confirm `.env` remains ignored.

**Verification result:** The effective local settings include `*`. A Django test client request with a dynamically generated CodeRange-style host passes host validation. All 30 Django tests pass, and `.venv/bin/python manage.py check` reports no issues.

### Phase 3: Commit and rendezvous

- [x] Review the diff and commit the change as `1cd75f1 fix: allow CodeRange hosts in local development`.
- [ ] Fast-forward merge the implementation branch into `main` and rerun checks after the merge.
- [ ] Update the task board with the merge and verification result.

### Phase 4: Sync living docs

- [ ] Update or add a focused `doc/wiki/` page for local CodeRange host configuration.
- [ ] Record the local-only wildcard behavior in `doc/wiki/footguns/` because `ALLOWED_HOSTS = ["*"]` accepts arbitrary Host headers and must not be used with debug mode off.
- [ ] Keep the documentation scoped to behavior supported by the settings and tests. Do not change `doc/canonical/`.

## Acceptance Criteria

- A request with a changing CodeRange-style hostname passes Django host validation in local debug mode without a hostname-specific source-code change.
- The default local configuration and `.env.example` include `*` through `DJANGO_ALLOWED_HOSTS` and retain localhost entries.
- A wildcard is rejected when debug mode is off.
- No `.env` credential values or session-specific hostname are added to tracked files.
- Django checks and tests pass before and after the merge to `main`.
- Living docs explain this behavior only after rendezvous.
