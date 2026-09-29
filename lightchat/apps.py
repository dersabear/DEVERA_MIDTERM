from django.apps import AppConfig


class LightchatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lightchat"

    def ready(self):
        from . import signals  # noqa: F401
