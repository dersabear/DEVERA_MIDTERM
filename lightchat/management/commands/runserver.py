from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticFilesRunserverCommand,
)
from django.contrib.staticfiles.views import serve as serve_static
from django.core.management.commands.runserver import Command as BaseRunserverCommand


class ScriptNameAwareStaticFilesHandler(StaticFilesHandler):
    def serve(self, request):
        return serve_static(request, self.file_path(request.path_info), insecure=True)


class Command(StaticFilesRunserverCommand):
    def get_handler(self, *args, **options):
        handler = BaseRunserverCommand.get_handler(self, *args, **options)
        if options["use_static_handler"] and (settings.DEBUG or options["insecure_serving"]):
            return ScriptNameAwareStaticFilesHandler(handler)
        return handler
