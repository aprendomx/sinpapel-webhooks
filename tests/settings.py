"""Minimal Django settings for sinpapel-webhooks test suite.

Mirrors sinpapel/tests/settings.py + adds sinpapel_webhooks app + tests.
"""
SECRET_KEY = "test-secret-key-not-for-production"  # noqa: S105
DEBUG = True

import os

# PostgreSQL required: WebhookSubscription uses JSONField `events__contains`
# lookup, which SQLite does not support (only PG/MySQL/Oracle).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("SINPAPEL_WEBHOOKS_TEST_DB", "sinpapel_webhooks_test"),
        "USER": os.environ.get("PGUSER", os.environ.get("USER", "")),
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": os.environ.get("PGHOST", ""),
        "PORT": os.environ.get("PGPORT", ""),
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "simple_history",
    "sinpapel",
    "sinpapel_webhooks",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

SINPAPEL_SIGNATURE_BACKEND = "sinpapel.signing.backends.fake.FakeBackend"

# Webhooks defaults — inline backend (sync) to keep tests deterministic
SINPAPEL_WEBHOOKS_BACKEND = "inline"

# URL config: mount the sinpapel-webhooks URLConf at root for inbound view tests
ROOT_URLCONF = "tests.urls"
