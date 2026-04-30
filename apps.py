from django.apps import AppConfig


class SinpapelWebhooksConfig(AppConfig):
    name = "sinpapel_webhooks"
    verbose_name = "Sinpapel Webhooks (event-driven HTTP)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Signal connections en T4 (S14.1) — loose coupling con sinpapel core.
        # Por ahora, skeleton sin signals para que migration de modelos en T2
        # pueda correr sin import side-effects.
        pass
