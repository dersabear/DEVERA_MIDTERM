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

The project reads local values from `.env` in the repository root. `.env` is ignored by Git. `.env.example` contains no provider credentials; secret variable placeholders are blank. `LIGHTCHAT_PROVIDER_MODE=mock` keeps deterministic responses. Set it to `litechat` to send real requests through the course proxy. Keep provider keys in the ignored `.env` file only.

For local CodeRange development, `DJANGO_ALLOWED_HOSTS` includes `*` while `DJANGO_DEBUG=true`. This accepts rotating forwarded preview hostnames without a session-specific host entry. Do not use the wildcard when debug mode is off; settings reject that combination. Set an explicit host list for any non-local environment.

LightChat's `ForwardedPrefixMiddleware` applies the request's WSGI `SCRIPT_NAME` to Django URL generation. In debug mode, it uses `X-Forwarded-Prefix` when `SCRIPT_NAME` is empty. If the proxy supplies neither value, set `LIGHTCHAT_BASE_PATH` in `.env` (for example, `/proxy/8000`). It is blank by default, so local URLs stay at the root. Navigation, form actions, and static links use the prefix. In configured fallback mode, root-relative `Location` headers omit it because CodeRange adds the mount path to redirects. The project `runserver` staticfiles handler serves assets at the local root and under the forwarded path.

Do not place secret values in source files, templates, browser storage, logs, README files, chat messages, or commits. Do not paste them into issue reports or assistant conversations.

The LiteChat proxy root defaults to `https://proxy.litechat.ai`. The app sends OpenAI, Anthropic, and Google requests to their documented provider routes. It reads provider keys from `LITECHAT_OPENAI_CREDENTIAL`, `LITECHAT_ANTHROPIC_CREDENTIAL`, and `LITECHAT_GOOGLE_CREDENTIAL`. These setting values are server-side only and must not be added to source control.

The chat provides Low, Medium, and High thinking effort per request. OpenAI uses `reasoning_effort`; Gemini 3.8 Flash uses `thinkingConfig.thinkingLevel`. The current LiteChat route rejects enabled thinking for Claude Haiku 4.5, so its effort selector is disabled and the existing disabled-thinking payload remains. Mock-only options also disable effort. The selection remains in the current chat UI state and is not stored in the database.

## Test

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
```

## Scope

This is a classroom simulation. Credits are fictional. It has no real payment processing. File size defaults to 10 MiB and can be changed with `LIGHTCHAT_MAX_UPLOAD_BYTES`. PDF and text files are parsed locally. PNG/JPEG attachments are accepted only by model options that declare image support; the image demo uses deterministic mock output.
