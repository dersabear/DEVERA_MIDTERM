# Local Development

LightChat loads local environment values from `.env` in the repository root. Start from `.env.example`; keep `.env` untracked.

The Django app reads `DJANGO_ALLOWED_HOSTS` as a comma-separated list. The local example includes `127.0.0.1`, `localhost`, and `*`. The settings fallback uses the same list when the variable is unset or empty and `DJANGO_DEBUG=true`.

The wildcard supports CodeRange's changing forwarded preview host without a session-specific hostname. Django raises `ImproperlyConfigured` if `*` is present while `DJANGO_DEBUG=false`. For any non-local environment, set `DJANGO_DEBUG=false` and provide an explicit host list.

The app does not enable `USE_X_FORWARDED_HOST`. It validates the `Host` value that Django receives from the local forwarding setup.

Run the local app with:

```sh
.venv/bin/python manage.py runserver
```

When CodeRange mounts the app below a forwarded path, Django must receive the WSGI `SCRIPT_NAME`. LightChat uses it to build static URLs for `app.css` and `app.js`. The project's `runserver` command also uses a static handler that serves mounted assets from `PATH_INFO`. This supports changing preview paths without a host or port in settings. See [Static Assets](static-assets.md) for the implementation details.
