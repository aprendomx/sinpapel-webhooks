"""Inline delivery backend (S14.1 + S14.2 refactor, ADR-013).

Sync delivery sin retry — for dev / smoke / very low volume.

S14.2 refactor: delega a `executor.execute_delivery(allow_retry=False)`. Compartido
con OutboxBackend (allow_retry=True). Inline conserva semántica: fire-and-forget
sin retry, primer fail → status="failed".

**NO usar en producción** sin entender que:
- Bloquea Django request worker durante el POST.
- Primer fail → status="failed"; sin reintento automático.
- Outbox backend (S14.2 default prod) maneja retry con backoff exponencial.
"""
from __future__ import annotations

from .. import executor
from ..ports import DeliveryResult


class InlineBackend:
    """Sync delivery; no retry; status persisted via shared executor."""

    name: str = "inline"

    def enqueue(self, delivery_id: int) -> None:
        """Sync execution — llama directamente deliver_now."""
        self.deliver_now(delivery_id)

    def deliver_now(self, delivery_id: int) -> DeliveryResult:
        """Ejecuta POST + persiste status. Sin retry (allow_retry=False)."""
        return executor.execute_delivery(delivery_id, allow_retry=False)
