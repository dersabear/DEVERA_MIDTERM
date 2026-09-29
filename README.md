# LightChat

LightChat is a classroom Django application. It uses SQLite, Django templates, local media storage, and a deterministic mock provider. Mock responses are clearly labelled and do not come from OpenAI, Anthropic, or Google.

## Run locally

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Open `http://127.0.0.1:8000/` and create an account. Each new account receives 100 test credits. Mock model costs are configured in `lightchat/catalog.py`.

## Local environment values

The project reads local values from `.env` in the repository root. `.env` is ignored by Git. `.env.example` contains no provider credentials; secret variable placeholders are blank. Keep `LIGHTCHAT_PROVIDER_MODE=mock` while the LiteChat proxy contract is unavailable. The app does not make real provider calls in mock mode.

For local CodeRange development, `DJANGO_ALLOWED_HOSTS` includes `*` while `DJANGO_DEBUG=true`. This accepts rotating forwarded preview hostnames without a session-specific host entry. Do not use the wildcard when debug mode is off; settings reject that combination. Set an explicit host list for any non-local environment.

LightChat's static links use the request's WSGI `SCRIPT_NAME` when mounted below a forwarded path. The project `runserver` command uses a staticfiles handler that serves from `PATH_INFO`, so both app assets work under CodeRange's changing preview path and at the local root. The forwarding server must supply `SCRIPT_NAME`; the app does not store a session URL or port.

Do not place secret values in source files, templates, browser storage, logs, README files, chat messages, or commits. Do not paste them into issue reports or assistant conversations.

The proxy URL, authentication scheme, request/response format, model IDs, and image protocol are not available in the project materials. The corresponding variables are reserved for a later verified integration. Adding values to `.env` does not enable live calls.

## Test

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
```

## Scope

This is a classroom simulation. Credits are fictional. It has no real payment processing. File size defaults to 10 MiB and can be changed with `LIGHTCHAT_MAX_UPLOAD_BYTES`. PDF and text files are parsed locally. PNG/JPEG attachments are accepted only by model options that declare image support; the image demo uses deterministic mock output.
