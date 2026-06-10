from django.apps import AppConfig


class GatingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gating"
    label = "gating"
    verbose_name = "Gating & Access Control"

    def ready(self):
        # Import signals (if any)
        try:
            from . import signals  # noqa
        except ImportError:
            pass