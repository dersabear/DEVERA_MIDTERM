# Static Assets

LightChat stores its app assets in `lightchat/static/lightchat/`. Templates use the `lightchat_static` tag. `ForwardedPrefixMiddleware` applies the request's WSGI `SCRIPT_NAME`, or the debug-only `X-Forwarded-Prefix` fallback, before Django renders URLs. The tag uses that prefix for `/static/` and leaves URLs at `/static/` for normal local development.

The local `runserver` command is provided by the `lightchat` app. It wraps Django's staticfiles handler so file lookup uses `request.path_info` and removes a duplicated forwarded prefix when needed. `request.path` includes `SCRIPT_NAME` and can cause a forwarded static request to miss the file.

The CodeRange preview host is not part of application settings. Use WSGI `SCRIPT_NAME` when available. In debug mode, the app also accepts the standard `X-Forwarded-Prefix` header when `SCRIPT_NAME` is empty. If the proxy sends neither, set `LIGHTCHAT_BASE_PATH` in `.env`; it is blank by default. The middleware ignores the forwarded header when debug mode is off.
