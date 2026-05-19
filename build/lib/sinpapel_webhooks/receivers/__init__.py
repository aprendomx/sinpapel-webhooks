"""sinpapel-webhooks inbound receiver framework (S14.4).

Decorator-based handler registration + dispatcher con HMAC verify + idempotency
dedup + URL routing en `sinpapel_webhooks/urls.py` propio (D1 architectural
deviation: NOT en sinpapel_drf).

Public API:
    from sinpapel_webhooks import webhook_receiver

    @webhook_receiver(source="baz", event="payment.confirmed")
    def handle_baz_payment(payload: dict, request) -> dict:
        return {"acked": True, "pago_id": payload["pago_id"]}
"""
from .registry import InboundReceiverRegistry, webhook_receiver

__all__ = ["InboundReceiverRegistry", "webhook_receiver"]
