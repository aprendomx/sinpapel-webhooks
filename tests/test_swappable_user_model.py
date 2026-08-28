"""Regresión: sinpapel-webhooks debe soportar un AUTH_USER_MODEL custom.

Hasta 0.2.3, `WebhookSubscription.created_by` declaraba el FK con el literal
"auth.User". Con un usuario custom, Django aborta el system check con
`fields.E301` (el campo y su `HistoricalWebhookSubscription`) y el proyecto no
arranca.

El check corre en un subproceso porque AUTH_USER_MODEL no se puede cambiar
dentro de un proceso Django ya inicializado.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_ENV = {
    "DJANGO_SETTINGS_MODULE": "tests.settings_swappable_user",
    "PATH": "/usr/bin:/bin",
}


def test_created_by_resolves_to_configured_user_model():
    """`created_by` apunta al modelo de `AUTH_USER_MODEL`, no a uno fijo."""
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from sinpapel_webhooks.models import WebhookSubscription

    field = WebhookSubscription._meta.get_field("created_by")
    assert field.remote_field.model is get_user_model(), (
        f"WebhookSubscription.created_by debe resolver a "
        f"{settings.AUTH_USER_MODEL}, no a un modelo fijo."
    )


def test_system_check_passes_with_swapped_user_model():
    """`manage.py check` pasa limpio con AUTH_USER_MODEL custom."""
    proc = subprocess.run(
        [sys.executable, "-m", "django", "check"],
        cwd=REPO_ROOT,
        env=_ENV,
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode == 0, (
        "sinpapel-webhooks no soporta AUTH_USER_MODEL custom:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def test_migrate_succeeds_with_swapped_user_model():
    """`migrate` aplica el esquema completo con AUTH_USER_MODEL custom."""
    proc = subprocess.run(
        [sys.executable, "-m", "django", "migrate", "-v", "0"],
        cwd=REPO_ROOT,
        env=_ENV,
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode == 0, (
        "migrate falla con AUTH_USER_MODEL custom:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
