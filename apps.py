from django.apps import AppConfig


class SinpapelWebhooksConfig(AppConfig):
    name = "sinpapel_webhooks"
    verbose_name = "Sinpapel Webhooks (event-driven HTTP)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Loose coupling: import signals para registrar @receiver decorators.
        # sinpapel core NO importa nada de sinpapel_webhooks; webhooks listens
        # via signal.connect a sinpapel models declarados con sender="sinpapel.X".
        from . import signals  # noqa: F401
