# Static Assets Behind a Forwarded Prefix

- **Study date:** 2026-09-29
- **Unix timestamp:** `1790666629`
- **Purpose:** Find why Django static assets use root URLs when LightChat runs below a CodeRange path prefix.
- **Status:** Study only. No application code was changed in this stage.

## Current State

LightChat sets `STATIC_URL = "static/"`. The base template uses Django's `{% static %}` tag for `lightchat/app.css` and `lightchat/app.js`.

In this workspace, a Django test-client request to `/login/` with `SCRIPT_NAME=/proxy/8000` still rendered static asset URLs as `/static/lightchat/app.css` and `/static/lightchat/app.js`. Those root URLs do not pass through CodeRange's `/proxy/8000/` route. The browser therefore receives a 404 instead of the app assets.

The `SCRIPT_NAME` value is the standard WSGI mount prefix. The CodeRange route can change, so the app must read the prefix for each request. It must not store a session hostname or proxy port in source code or settings.

## Relevant Django Behavior

- `django.contrib.staticfiles` provides static-file lookup and development serving through `runserver` when `DEBUG=True`.
- `{% static %}` calls the configured static storage to make the URL. In this app, that output is not request-prefix-aware after static storage has been initialized.
- Django exposes the WSGI mount prefix on `request.META["SCRIPT_NAME"]`. A custom template tag can use that per-request value to build the static URL.
- With CodeRange's prefix removed before Django routes the request, the proxied asset request should reach Django as `SCRIPT_NAME=/proxy/<port>` and `PATH_INFO=/static/...`. Django's staticfiles development handler can then serve the file.
- `STATIC_URL` should remain a stable path, `/static/`. A request-aware tag should add `SCRIPT_NAME` only when it is present. With an empty script name, local URLs stay `/static/...`.

Do not enable `USE_X_FORWARDED_HOST` for this fix. The static URL needs a path prefix, not a different host. Do not derive asset paths from a hostname or a fixed `/proxy/8000` value.

## Recommended Fix

Add a small LightChat template tag that combines the request's `SCRIPT_NAME` with the configured static URL. Use this tag for the app CSS and JavaScript in the shared base template. Keep Django's normal staticfiles handler and `STATIC_URL` for local development.

The tag must preserve normal local behavior when `SCRIPT_NAME` is empty. It must also support any forwarded prefix without special knowledge of CodeRange's session route.

## Verification

- Render the login page with `SCRIPT_NAME=/proxy/<dynamic-port>` and verify the CSS and JavaScript URLs contain that prefix.
- Request both assets through a Django staticfiles handler with a forwarded `SCRIPT_NAME` and verify HTTP 200 and correct content types.
- Verify the same assets return HTTP 200 with an empty script name and normal local URLs.
- Verify the login page renders the prefixed links and its login/sign-up controls remain present.
- Run Django checks and the full test suite after implementation and after the merge to `main`.

## Sources

- Django 5.2, static files: <https://docs.djangoproject.com/en/5.2/howto/static-files/>
- Django 5.2, `STATIC_URL` and `FORCE_SCRIPT_NAME`: <https://docs.djangoproject.com/en/5.2/ref/settings/#static-url> and <https://docs.djangoproject.com/en/5.2/ref/settings/#force-script-name>
