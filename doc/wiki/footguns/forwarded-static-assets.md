# Forwarded Static Assets

LightChat's `ForwardedPrefixMiddleware` applies WSGI `SCRIPT_NAME` to Django URL generation. If it is empty, debug mode can use `X-Forwarded-Prefix`. If the proxy sends neither, configure `LIGHTCHAT_BASE_PATH` in `.env`. This setting is blank by default and may need an update when a session-specific proxy port changes. Do not rely on `X-Forwarded-Prefix` outside debug mode; production servers must set WSGI `SCRIPT_NAME` or configure `LIGHTCHAT_BASE_PATH`.

When `LIGHTCHAT_BASE_PATH` is the fallback, outgoing root-relative `Location` headers intentionally omit the base path. CodeRange adds the mount path to redirects. Adding the base path to those redirect headers again creates `/proxy/<port>/proxy/<port>/...` URLs. Rendered links and form actions still include the configured prefix.

Django's standard `runserver` static handler can receive a path with the mount prefix still present. Its default file lookup can then produce a 404 for valid static files. LightChat's development `runserver` command strips a duplicate prefix and serves from `request.path_info`.

Use `python manage.py runserver` for the local demo. Do not use `--nostatic` when you want Django's development server to serve these files. This handler is for development only; production deployments must serve collected static files with their configured static server.
