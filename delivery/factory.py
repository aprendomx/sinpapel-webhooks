"""Delivery backend factory (ADR-013, D7 settings call-time).

Resuelve `SINPAPEL_WEBHOOKS_BACKEND` setting:
- Short-names: "inline", "outbox", "celery"
- Dotted-path: "myproject.webhooks.MyCustomBackend"

Cached vía `lru_cache` resetable con `get_delivery_backend.cache_clear()`
(útil en tests con `override_settings`).
"""
from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .ports import WebhookDeliveryBackend


_SHORT_NAME_PATHS: dict[str, str] = {
    "inline": "sinpapel_webhooks.delivery.backends.inline.InlineBackend",
    "outbox": "sinpapel_webhooks.delivery.backends.outbox.OutboxBackend",
    # S14.3:
    # "celery": "sinpapel_webhooks.delivery.backends.celery.CeleryBackend",
}


@lru_cache(maxsize=1)
def get_delivery_backend() -> WebhookDeliveryBackend:
    """Resolve + instanciar el delivery backend configurado.

    Returns:
        Instance del backend (singleton vía lru_cache).

    Raises:
        ImproperlyConfigured: si setting inválido o backend no implementa Protocol.
    """
    setting_value = getattr(settings, "SINPAPEL_WEBHOOKS_BACKEND", "inline")

    dotted_path = _SHORT_NAME_PATHS.get(setting_value, setting_value)

    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
    except ValueError as e:
        raise ImproperlyConfigured(
            f"SINPAPEL_WEBHOOKS_BACKEND must be a short-name "
            f"({', '.join(_SHORT_NAME_PATHS)}) or dotted path. Got: {setting_value!r}"
        ) from e

    try:
        module = import_module(module_path)
        backend_cls = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImproperlyConfigured(
            f"Could not import delivery backend {dotted_path!r}: {e}"
        ) from e

    instance = backend_cls()

    if not isinstance(instance, WebhookDeliveryBackend):
        raise ImproperlyConfigured(
            f"{dotted_path!r} does not implement WebhookDeliveryBackend Protocol "
            f"(missing `name`, `enqueue`, or `deliver_now`)"
        )

    return instance
