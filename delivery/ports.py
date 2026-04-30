"""Delivery port + result type (ADR-013).

`WebhookDeliveryBackend` Protocol define la interfaz que cada adapter
implementa (inline / outbox / celery / custom). `@runtime_checkable` permite
isinstance() validation en factory para detectar misconfigured backends.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class DeliveryResult:
    """Resultado de un intento de delivery.

    Attributes:
        success: True si HTTP 2xx, False otherwise.
        status_code: HTTP status code; None si timeout/connection error.
        response_body: body de respuesta (truncado a ~5000 chars).
        error: error message si success=False (timeout/connection/etc).
        should_retry: True si el backend debe re-encolar (S14.2).
        next_retry_at: timestamp del próximo intento (S14.2 backoff).
    """

    success: bool
    status_code: int | None
    response_body: str
    error: str | None = None
    should_retry: bool = False
    next_retry_at: datetime | None = None


@runtime_checkable
class WebhookDeliveryBackend(Protocol):
    """Protocol para delivery backends.

    Implementaciones provistas:
    - InlineBackend (S14.1): sync delivery sin retry.
    - OutboxBackend (S14.2): DB-backed queue + worker command.
    - CeleryBackend (S14.3): gated extra `[celery]`.

    Custom backends: consumer puede implementar este Protocol y configurar
    `SINPAPEL_WEBHOOKS_BACKEND` con dotted-path.
    """

    name: str

    def enqueue(self, delivery_id: int) -> None:
        """Encola/ejecuta delivery. Llamado post-commit desde signal handler.

        Implementaciones:
        - inline: ejecuta `requests.post()` inmediatamente; sin retry.
        - outbox: no-op (worker pollea DB); el delivery ya está persistido.
        - celery: dispatcha task `deliver_webhook.delay(delivery_id)`.
        """

    def deliver_now(self, delivery_id: int) -> DeliveryResult:
        """Ejecución blocking explícita.

        Usado por worker (outbox) y retry manual (admin endpoint S14.5).
        Backends pueden implementar este método incluso si `enqueue` es async.
        """
