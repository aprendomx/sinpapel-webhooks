"""Outbox delivery backend (S14.2 / T3, ADR-013).

Default production backend — DB-backed queue sin broker dependency.

Semantics:
- `enqueue(delivery_id)`: **no-op**. La WebhookDelivery ya está persistida con
  status="pending" por emit_event. Worker la recoge en próximo poll cycle.
- `deliver_now(delivery_id)`: blocking execution con `allow_retry=True`. Usado por
  worker (sinpapel_webhooks_worker command) y manual retry (S14.5 admin endpoint).

Retry behavior (delegated a executor + retry policy):
- 5xx/timeout/connection → status="pending" + scheduled_at=now+backoff (con jitter ±10%)
- 4xx semantic (400/401/403/404/410/422) → status="failed" sin retry
- Max attempts exhausted → status="dead_letter" (default) o "failed"
"""
from __future__ import annotations

from .. import executor
from ..ports import DeliveryResult


class OutboxBackend:
    """DB-backed queue; worker drains pending deliveries con retry-aware logic."""

    name: str = "outbox"

    def enqueue(self, delivery_id: int) -> None:
        """No-op — WebhookDelivery ya persistida con status="pending".

        El worker (sinpapel_webhooks_worker management command) la recogerá
        en su próximo poll cycle. Loose coupling: signal handler no bloquea
        Django request worker esperando HTTP response.
        """
        # Intentionally empty — DB persistence happens upstream en emit_event.

    def deliver_now(self, delivery_id: int) -> DeliveryResult:
        """Ejecuta delivery via shared executor con retry-aware semantics.

        Llamado por:
        - Worker management command (long-running poller)
        - Manual retry endpoint (S14.5 admin)
        """
        return executor.execute_delivery(delivery_id, allow_retry=True)
