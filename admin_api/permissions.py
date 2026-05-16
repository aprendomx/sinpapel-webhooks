"""Permission resolver — reads SINPAPEL_WEBHOOKS_ADMIN_PERMISSION setting."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

DEFAULT_PERMISSION_DOTTED = "rest_framework.permissions.IsAdminUser"


def get_admin_permission_class() -> Any:
    """Resolve the configured permission class.

    Reads `SINPAPEL_WEBHOOKS_ADMIN_PERMISSION` (dotted path); defaults to
    `rest_framework.permissions.IsAdminUser`.

    Raises:
        ImproperlyConfigured: if the dotted path cannot be imported.
    """
    dotted = getattr(settings, "SINPAPEL_WEBHOOKS_ADMIN_PERMISSION", DEFAULT_PERMISSION_DOTTED)
    try:
        return import_string(dotted)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"SINPAPEL_WEBHOOKS_ADMIN_PERMISSION={dotted!r} could not be imported: {exc}"
        ) from exc
