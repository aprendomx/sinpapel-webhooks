# sinpapel-webhooks — event-driven HTTP communication for sinpapel.
# Copyright (C) 2024-2026 Julio Adrián <jadrian.s@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Celery delivery backend (S14.3, ADR-013).

Distributed delivery via Celery shared_task. Gated por extra `[celery]`:

    pip install sinpapel-webhooks[celery]

Use case: high-volume consumers (>1000 events/min) con Celery + broker existente
(Redis/RabbitMQ). Reusa shared `executor.execute_delivery(allow_retry=True)` —
mismo retry policy + envelope + HMAC signing que outbox; diferente dispatch
mechanism.

Tests usan `@override_settings(CELERY_TASK_ALWAYS_EAGER=True)` para sync execution
sin broker.
"""
from __future__ import annotations

try:
    from celery import shared_task
except ImportError as e:
    raise ImportError(
        "CeleryBackend requires `pip install sinpapel-webhooks[celery]`"
    ) from e

from .. import executor
from ..ports import DeliveryResult


@shared_task(name="sinpapel_webhooks.deliver")
def _deliver_webhook_task(delivery_id: int) -> dict:
    """Celery task — wraps executor con allow_retry=True semantics.

    En eager mode (`CELERY_TASK_ALWAYS_EAGER=True`), ejecuta sync. En production
    (broker configured), Celery routea task al worker pool.

    Returns: dict simple con success + status_code + delivery_id (debe ser
    JSON-serializable per Celery requirements; NO retornar DeliveryResult dataclass
    directamente — se serializa primitives).
    """
    result = executor.execute_delivery(delivery_id, allow_retry=True)
    return {
        "success": result.success,
        "status_code": result.status_code,
        "delivery_id": delivery_id,
    }


class CeleryBackend:
    """Distributed delivery via Celery; gated por extra [celery]."""

    name: str = "celery"

    def enqueue(self, delivery_id: int) -> None:
        """Dispatcha task a Celery worker pool (async)."""
        _deliver_webhook_task.delay(delivery_id)

    def deliver_now(self, delivery_id: int) -> DeliveryResult:
        """Blocking execution via shared executor con retry-aware semantics.

        Llamado por:
        - Manual retry endpoint (S14.5 admin)
        - Direct invocation cuando consumer wants sync execution sin task overhead.
        """
        return executor.execute_delivery(delivery_id, allow_retry=True)
