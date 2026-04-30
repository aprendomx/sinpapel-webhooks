"""Inline delivery backend (S14.1, ADR-013).

Sync delivery sin retry — for dev / smoke / very low volume.
**NO usar en producción** sin entender que:
- Bloquea Django request worker durante el POST.
- Primer fail → status="failed"; sin reintento automático.
- Outbox backend (S14.2, default prod) maneja retry con backoff exponencial.
"""
from __future__ import annotations

import json
import time

import requests
from django.conf import settings
from django.utils import timezone

from .. import ports
from ...models import WebhookDelivery
from ...signing import compute_signature


# 4xx semánticos que NO deben retry (config error, no transient)
NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 410, 422})


class InlineBackend:
    """Sync delivery; no retry; status persisted."""

    name: str = "inline"

    def enqueue(self, delivery_id: int) -> None:
        """Sync execution — llama directamente deliver_now."""
        self.deliver_now(delivery_id)

    def deliver_now(self, delivery_id: int) -> ports.DeliveryResult:
        """Ejecuta POST + persiste status. Sin retry."""
        delivery = (
            WebhookDelivery.objects
            .select_related("subscription", "event")
            .get(pk=delivery_id)
        )
        delivery.status = WebhookDelivery.STATUS_DELIVERING
        delivery.attempts += 1
        delivery.last_attempt_at = timezone.now()
        delivery.save(update_fields=["status", "attempts", "last_attempt_at"])

        # Build request
        from sinpapel_webhooks import __version__ as wh_version
        payload_bytes = json.dumps(delivery.event.payload, default=str).encode()
        ts = int(time.time())
        signature = compute_signature(
            payload_bytes, delivery.subscription.secret, timestamp=ts,
        )
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Sinpapel-Signature": signature,
            "X-Sinpapel-Event-Id": str(delivery.event.event_id),
            "X-Sinpapel-Event-Type": delivery.event.event_type,
            "X-Sinpapel-Webhook-Id": str(delivery.subscription.id),
            "User-Agent": f"sinpapel-webhooks/{wh_version}",
        }
        timeout = getattr(settings, "SINPAPEL_WEBHOOKS_REQUEST_TIMEOUT", 10)

        try:
            response = requests.post(
                delivery.subscription.url,
                data=payload_bytes,
                headers=headers,
                timeout=timeout,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            delivery.status = WebhookDelivery.STATUS_FAILED
            delivery.last_error = str(e)
            delivery.save(update_fields=["status", "last_error"])
            return ports.DeliveryResult(
                success=False,
                status_code=None,
                response_body="",
                error=str(e),
            )

        success = 200 <= response.status_code < 300
        delivery.status = (
            WebhookDelivery.STATUS_DELIVERED if success else WebhookDelivery.STATUS_FAILED
        )
        delivery.last_response_status = response.status_code
        # Truncate response body to avoid bloating DB with massive bodies
        delivery.last_response_body = (response.text or "")[:5000]
        delivery.save(update_fields=["status", "last_response_status", "last_response_body"])

        return ports.DeliveryResult(
            success=success,
            status_code=response.status_code,
            response_body=response.text,
        )
