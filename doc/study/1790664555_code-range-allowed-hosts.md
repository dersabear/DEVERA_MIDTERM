# CodeRange Host Validation Study

- **Study date:** 2026-09-29
- **Unix timestamp:** `1790664555`
- **Purpose:** Identify a safe, session-independent way to let the local Django app accept CodeRange's forwarded host.
- **Status:** Study only. No application code was changed in this stage.

## Current State

The application already reads `DJANGO_ALLOWED_HOSTS` in `lightchat_site/settings.py`. The current fallback and `.env.example` allow only `127.0.0.1` and `localhost`. The repository does not contain a local `.env` file. Therefore a forwarded CodeRange hostname can fail Django's host check and raise `DisallowedHost`.

The current browser session hostname is not available in the workspace. Do not add a session-specific hostname to source control or configuration examples.

## Django Behavior

Django compares the request `Host` header with `ALLOWED_HOSTS`. A host that does not match causes `request.get_host()` to raise `DisallowedHost`.

Django supports these relevant entries:

- An exact host name, such as `localhost`.
- A leading-dot suffix, such as `.example.com`, which matches the base domain and its subdomains.
- The value `*`, which matches all hosts. Django states that an application must then provide its own host validation.

A leading-dot suffix is the narrowest choice when the platform's stable parent domain is known. That domain is not available in this workspace, and guessing it can keep the error in place. A session-specific hostname is also unstable.

## Options

| Option | Benefit | Risk or limit |
| --- | --- | --- |
| Add the current forwarded hostname | Narrow permission | The session host can change and must not be hard-coded. |
| Add a fixed CodeRange domain suffix | Supports any session under that suffix | The stable suffix is not known from available materials. Guessing it is not reliable. |
| Allow `*` in local debug configuration | Accepts any forwarded CodeRange hostname without a session-specific value | Accepts any Host header. It must not be enabled outside local development. |

## Recommendation

For this classroom app, allow `*` through `DJANGO_ALLOWED_HOSTS` only when `DJANGO_DEBUG=true`. Keep localhost entries. Reject wildcard configuration when debug mode is off. This uses Django's existing setting and does not guess a CodeRange domain.

The local `.env.example` should show the wildcard. The settings fallback should also support CodeRange when the user has not created `.env` yet. The actual `.env` must remain local and ignored by Git.

Do not enable `USE_X_FORWARDED_HOST` as part of this change. The report identifies a forwarded host, but it does not establish that the proxy uses the `X-Forwarded-Host` header. Enabling that setting without confirming the proxy behavior can trust an unverified header.

## Verification

- Confirm that a dynamically named CodeRange-style host is accepted when debug mode is on.
- Confirm that the same wildcard setting is rejected when debug mode is off.
- Run Django system checks and the full test suite.
- Re-check that the change contains no session-specific host and that the actual `.env` file is not tracked.

## Source

- Django 5.2 settings documentation, `ALLOWED_HOSTS`: <https://docs.djangoproject.com/en/5.2/ref/settings/#allowed-hosts>
