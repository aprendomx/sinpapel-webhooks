"""Inbound webhook dispatcher (S14.4 / T2).

Orquesta 9 steps documented en design.md §3:
1. Read body bytes (D9: request.body)
2. Lookup secret (D8: SINPAPEL_WEBHOOKS_INBOUND_SECRETS) → 401 si missing
3. HMAC verify (signing.verify_signature) → 401 si falla
4. Parse event headers → 400 si missing
5. Parse JSON body → 400 si invalid
6. Idempotency get_or_create (D5) → 200 duplicate sin re-invoke
7. Lookup handler (Registry.get) → 404 si missing
8. Invoke handler → 500 si exception
9. Return result (dict) o {"acked": True} default
"""
from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from ..exceptions import WebhookSignatureError
from ..models import InboundWebhookEvent
from ..signing import verify_signature
from .registry import InboundReceiverRegistry


class ReceiverDispatcher:
    """Inbound webhook dispatcher.

    Single-method interface: `dispatch(source, request) -> tuple[dict, int]`.
    Returns `(response_body, http_status_code)` para que view emita JsonResponse.
    """

    def dispatch(self, source: str, request: HttpRequest) -> tuple[dict[str, Any], int]:
        """Execute 9-step dispatch flow."""
        # Step 1: Read body bytes (D9 — byte-exact for HMAC)
        body = request.body  # bytes

        # Step 2: Lookup secret (D8)
        secrets = getattr(settings, "SINPAPEL_WEBHOOKS_INBOUND_SECRETS", {})
        secret = secrets.get(source)
        if secret is None:
            return ({"error": f"Unknown source: {source}"}, 401)

        # Step 3: HMAC verify
        sig_header = request.headers.get("X-Sinpapel-Signature", "")
        tolerance = getattr(settings, "SINPAPEL_WEBHOOKS_TIMESTAMP_TOLERANCE", 300)
        try:
            verify_signature(body, sig_header, secret, tolerance_seconds=tolerance)
        except WebhookSignatureError as e:
            return ({"error": str(e)}, 401)

        # Step 4: Parse event headers
        event_id = request.headers.get("X-Sinpapel-Event-Id")
        event_type = request.headers.get("X-Sinpapel-Event-Type")
        if not event_id or not event_type:
            return ({"error": "Missing X-Sinpapel-Event-Id or X-Sinpapel-Event-Type"}, 400)

        # Step 5: Parse JSON body
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return ({"error": "Invalid JSON body"}, 400)

        # Step 6: Idempotency check (D5 atomic via unique_together)
        inbound_event, created = InboundWebhookEvent.objects.get_or_create(
            source=source,
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload": payload,
                "handler_status": InboundWebhookEvent.HANDLER_DUPLICATE,
            },
        )
        if not created:
            # Already received — duplicate → 200 sin re-invoke
            return ({"acked": True, "duplicate": True}, 200)

        # Step 7: Lookup handler (D2 registry)
        handler = InboundReceiverRegistry.get(source, event_type)
        if handler is None:
            inbound_event.handler_status = InboundWebhookEvent.HANDLER_NO_HANDLER
            inbound_event.save(update_fields=["handler_status"])
            return ({"error": f"No handler for {source}/{event_type}"}, 404)

        # Step 8: Invoke handler
        try:
            result = handler(payload, request)
        except Exception as e:
            inbound_event.handler_status = InboundWebhookEvent.HANDLER_ERROR
            inbound_event.save(update_fields=["handler_status"])
            return ({"error": f"Handler raised: {type(e).__name__}: {e}"}, 500)

        inbound_event.handler_status = InboundWebhookEvent.HANDLER_PROCESSED
        inbound_event.save(update_fields=["handler_status"])

        # Step 9: Return handler result (D6 contract: dict | None)
        if isinstance(result, dict):
            return (result, 200)
        return ({"acked": True}, 200)
