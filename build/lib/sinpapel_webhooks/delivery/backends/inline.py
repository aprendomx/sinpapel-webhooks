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
