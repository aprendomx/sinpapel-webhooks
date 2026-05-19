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

"""emit_event helper — persiste WebhookEvent + crea WebhookDeliveries + enqueue.

Llamado desde signal handlers (sync, dentro de `transaction.on_commit` del caller),
o explícitamente por consumer code para custom events.

D1: subscription filter usa JSONField `events__contains` lookup.
D3: GFK source_object_ct/source_object_id populated cuando source provided.
"""
from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from .delivery.factory import get_delivery_backend
from .models import WebhookDelivery, WebhookEvent, WebhookSubscription


def emit_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    source: models.Model | None = None,
) -> WebhookEvent:
    """Emite un webhook event al ecosistema sinpapel-webhooks.

    Args:
        event_type: tipo canonical (ej. "workflow.transition.completed").
        payload: dict serializable a JSON con datos del evento.
        source: opcional — Model instance fuente. Si provisto, se persiste
                como GFK (source_object_ct + source_object_id) para linkback
                en admin.

    Returns:
        El WebhookEvent persistido. Las WebhookDeliveries creadas (si hay
        subscriptions matching) están accesibles vía `event.deliveries.all()`.

    Side effects:
        - Crea 1 WebhookEvent row.
        - Crea N WebhookDelivery rows (1 por subscription matching).
        - Llama backend.enqueue(delivery_id) por cada delivery creado.

    Notes:
        Caller es responsable de invocar dentro de `transaction.on_commit()`
        si quiere semantics post-commit. emit_event en sí NO usa on_commit
        — esto permite que signal handlers controlen el timing.
    """
    # 1. Persist canonical event
    source_ct = ContentType.objects.get_for_model(source) if source is not None else None
    source_id = source.pk if source is not None else None

    event = WebhookEvent.objects.create(
        event_type=event_type,
        payload=payload,
        source_object_ct=source_ct,
        source_object_id=source_id,
    )

    # 2. Find matching active subscriptions (D1: events__contains JSONField)
    subscriptions = (
        WebhookSubscription.objects
        .filter(active=True)
        .filter(events__contains=event_type)
    )

    # 3. Create deliveries + enqueue via configured backend
    if not subscriptions.exists():
        return event

    backend = get_delivery_backend()
    deliveries = [
        WebhookDelivery(subscription=sub, event=event)
        for sub in subscriptions
    ]
    WebhookDelivery.objects.bulk_create(deliveries)
    # bulk_create skips signals; we don't have signals on WebhookDelivery,
    # but we still need PKs. SQLite needs reload; PostgreSQL returns PKs.
    delivery_ids = list(
        WebhookDelivery.objects
        .filter(event=event, status=WebhookDelivery.STATUS_PENDING)
        .values_list("pk", flat=True)
    )
    for delivery_id in delivery_ids:
        backend.enqueue(delivery_id)

    return event
