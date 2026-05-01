"""Shared delivery executor (S14.2 / T1).

Compartido entre InlineBackend (allow_retry=False) y OutboxBackend
(allow_retry=True, S14.2 / T3). Encapsula:
- Build payload envelope (D4: event_id + event_type + occurred_at + data + metadata)
- HMAC signing
- POST request con headers X-Sinpapel-*
- Status persistence (delivered / failed / pending+retry / dead_letter)

`allow_retry` flag controla retry behavior:
- False (inline): primer fail → status="failed" inmediato, sin retry programado.
- True (outbox): según `should_retry()` — 5xx/timeout → schedule retry; 4xx semantic
  → failed; max attempts → dead_letter.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from sinpapel_webhooks import __version__ as webhooks_version
from sinpapel_webhooks.models import WebhookDelivery
from sinpapel_webhooks.signing import compute_signature

from .ports import DeliveryResult


def _get_sinpapel_version() -> str:
    """Lazy import sinpapel para evitar import order issues durante app loading."""
    try:
        from sinpapel import __version__ as v
        return v
    except ImportError:
        return "unknown"


def build_envelope(delivery: WebhookDelivery) -> dict[str, Any]:
    """Construye el payload envelope (D4) per-delivery.

    El envelope incluye `metadata.subscription_id` que varía per-delivery
    (un mismo WebhookEvent puede generar N deliveries con distinto subscription).
    Por eso el envelope se construye en executor (no en emit_event).
    """
    return {
        "event_id": str(delivery.event.event_id),
        "event_type": delivery.event.event_type,
        "occurred_at": delivery.event.occurred_at.isoformat(),
        "data": delivery.event.payload,
        "metadata": {
            "sinpapel_version": _get_sinpapel_version(),
            "webhooks_version": webhooks_version,
            "subscription_id": delivery.subscription_id,
            "api_version": "2026-04-30",
        },
    }


def execute_delivery(delivery_id: int, *, allow_retry: bool) -> DeliveryResult:
    """Ejecuta un delivery attempt: build envelope + sign + POST + persist status.

    Args:
        delivery_id: PK de WebhookDelivery a procesar.
        allow_retry: True → en transient failure, schedule retry vía scheduled_at;
                     False → primer fail → status="failed" sin retry (inline semantics).

    Returns:
        DeliveryResult con success, status_code, response_body, error, should_retry.
    """
    delivery = (
        WebhookDelivery.objects
        .select_related("subscription", "event")
        .get(pk=delivery_id)
    )

    # Mark delivering + increment attempts atomically
    delivery.status = WebhookDelivery.STATUS_DELIVERING
    delivery.attempts += 1
    delivery.last_attempt_at = timezone.now()
    delivery.save(update_fields=["status", "attempts", "last_attempt_at"])

    # Build envelope (D4) + sign
    envelope = build_envelope(delivery)
    payload_bytes = json.dumps(envelope, default=str).encode()
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
        "User-Agent": f"sinpapel-webhooks/{webhooks_version}",
    }
    timeout = getattr(settings, "SINPAPEL_WEBHOOKS_REQUEST_TIMEOUT", 10)

    # Execute POST
    try:
        response = requests.post(
            delivery.subscription.url,
            data=payload_bytes,
            headers=headers,
            timeout=timeout,
        )
    except (requests.Timeout, requests.ConnectionError) as e:
        result = DeliveryResult(
            success=False,
            status_code=None,
            response_body="",
            error=str(e),
        )
        _persist_failure(delivery, result, allow_retry=allow_retry)
        return result

    success = 200 <= response.status_code < 300
    result = DeliveryResult(
        success=success,
        status_code=response.status_code,
        response_body=response.text,
    )

    if success:
        _persist_success(delivery, result)
    else:
        _persist_failure(delivery, result, allow_retry=allow_retry)
    return result


def _persist_success(delivery: WebhookDelivery, result: DeliveryResult) -> None:
    delivery.status = WebhookDelivery.STATUS_DELIVERED
    delivery.last_response_status = result.status_code
    delivery.last_response_body = (result.response_body or "")[:5000]
    delivery.save(
        update_fields=["status", "last_response_status", "last_response_body"],
    )


def _persist_failure(
    delivery: WebhookDelivery,
    result: DeliveryResult,
    *,
    allow_retry: bool,
) -> None:
    """Persiste failure según semántica retry-aware (T2 retry policy aún no integrada)."""
    delivery.last_response_status = result.status_code
    delivery.last_response_body = (result.response_body or "")[:5000]
    if result.error:
        delivery.last_error = result.error

    if not allow_retry:
        # Inline semantics: primer fail → failed (no retry, no dead_letter)
        delivery.status = WebhookDelivery.STATUS_FAILED
        delivery.save(
            update_fields=[
                "status", "last_response_status", "last_response_body", "last_error",
            ],
        )
        return

    # T2 (retry policy) integrará compute_next_retry_at + dead_letter logic aquí.
    # Por ahora (post-T1, pre-T2): mismo comportamiento que inline (failed).
    # OutboxBackend en T3 sobreescribirá _persist_failure con retry-aware version.
    delivery.status = WebhookDelivery.STATUS_FAILED
    delivery.save(
        update_fields=[
            "status", "last_response_status", "last_response_body", "last_error",
        ],
    )
