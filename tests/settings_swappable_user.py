"""Settings con AUTH_USER_MODEL swapped, para el test de regresión de FKs.

`WebhookSubscription.created_by` debe declararse con `settings.AUTH_USER_MODEL`.
Con el literal "auth.User", cualquier proyecto con usuario custom aborta en el
system check con `fields.E301`.

SQLite basta: este settings solo se usa para `check` y `migrate`, no para los
tests que necesitan el lookup `events__contains` de PostgreSQL.
"""
from tests.settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "simple_history",
    "sinpapel",
    "sinpapel_webhooks",
    "tests.swappable_user",
]

AUTH_USER_MODEL = "swappable_user.CustomUser"
