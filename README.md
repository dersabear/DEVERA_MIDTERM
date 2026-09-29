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

The project reads local values from `.env` in the repository root. `.env` is ignored by Git. `.env.example` contains variable names with blank values only. Keep `LIGHTCHAT_PROVIDER_MODE=mock` while the LiteChat proxy contract is unavailable. The app does not make real provider calls in mock mode.

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
