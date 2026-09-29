# Static Assets

LightChat stores its app assets in `lightchat/static/lightchat/`. Templates use the `lightchat_static` tag. The tag adds the current WSGI `SCRIPT_NAME` to `/static/` when LightChat is mounted under a path, and leaves the URL at `/static/` for normal local development.

The local `runserver` command is provided by the `lightchat` app. It wraps Django's staticfiles handler so the file lookup uses `request.path_info` and not `request.path`. The latter includes `SCRIPT_NAME` and can cause a forwarded static request to miss the file.

The CodeRange preview host and proxy port are not part of application settings. The forwarding server must set WSGI `SCRIPT_NAME` for the mount prefix.
