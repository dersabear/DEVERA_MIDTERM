# CodeRange Host Allowlist

In local debug mode, LightChat allows `*` in `DJANGO_ALLOWED_HOSTS` so CodeRange preview hosts can change between sessions. Django's wildcard accepts any `Host` header. Do not use it with `DJANGO_DEBUG=false`; LightChat rejects that configuration at startup.

An explicit `DJANGO_ALLOWED_HOSTS` value replaces the default. If an existing root `.env` still lists only localhost, add `,*` for local CodeRange use. Updating `.env.example` does not update an existing `.env` file.

Do not add a session-specific preview hostname to source control. Do not enable `USE_X_FORWARDED_HOST` unless the forwarding contract is known and trusted.
