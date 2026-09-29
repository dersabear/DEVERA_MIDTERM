from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticFilesRunserverCommand,
)
from django.contrib.staticfiles.views import serve as serve_static
from django.core.handlers.wsgi import get_path_info
from django.core.management.commands.runserver import Command as BaseRunserverCommand

from lightchat.middleware import resolve_script_name


class ScriptNameAwareStaticFilesHandler(StaticFilesHandler):
    def __call__(self, environ, start_response):
        script_name = resolve_script_name(environ)
        path_info = get_path_info(environ)
        while script_name and (path_info == script_name or path_info.startswith(f"{script_name}/")):
            environ = environ.copy()
            environ["PATH_INFO"] = path_info[len(script_name):] or "/"
            path_info = environ["PATH_INFO"]
        return super().__call__(environ, start_response)

    def serve(self, request):
        path_info = request.path_info
        return serve_static(request, self.file_path(path_info), insecure=True)


class Command(StaticFilesRunserverCommand):
    def get_handler(self, *args, **options):
        handler = BaseRunserverCommand.get_handler(self, *args, **options)
        if options["use_static_handler"] and (settings.DEBUG or options["insecure_serving"]):
            return ScriptNameAwareStaticFilesHandler(handler)
        return handler
