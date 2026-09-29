# Forwarded Static Assets

LightChat prefixes its CSS and JavaScript URLs with WSGI `SCRIPT_NAME`. The forwarding server must set this value to the mount path. The app does not guess a CodeRange hostname, session identifier, or port.

Django's standard `runserver` static handler checks the path relative to the mount, but its default file lookup uses `request.path`, which includes the mount prefix. This can produce a 404 for valid static files under a forwarded path. LightChat's development `runserver` command uses a small handler that serves from `request.path_info` instead.

Use `python manage.py runserver` for the local demo. Do not use `--nostatic` when you want Django's development server to serve these files. This handler is for development only; production deployments must serve collected static files with their configured static server.
