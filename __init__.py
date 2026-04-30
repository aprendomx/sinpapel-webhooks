"""sinpapel-webhooks — event-driven HTTP communication para sinpapel.

Outbound: signal hooks escuchando eventos del dominio sinpapel
(workflow transitions, signatures, document changes) → POSTs HMAC-firmados
a URLs configuradas vía WebhookSubscription. Pluggable delivery backends
(inline / outbox / celery, ADR-013).

Inbound: receiver framework con @webhook_receiver decorator + HMAC verification
+ idempotency dedup. Routing en sinpapel-drf.

Las re-exports públicas (compute_signature, verify_signature, emit_event,
WebhookDeliveryBackend, etc.) se agregan progresivamente en S14.1-S14.6.
"""
__version__ = "0.1.0"

__all__ = ["__version__"]
