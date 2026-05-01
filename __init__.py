"""sinpapel-webhooks — event-driven HTTP communication para sinpapel.

Outbound: signal hooks escuchando eventos del dominio sinpapel
(workflow transitions, signatures, document changes) → POSTs HMAC-firmados
a URLs configuradas vía WebhookSubscription. Pluggable delivery backends
(inline / outbox / celery, ADR-013).

Inbound: receiver framework con @webhook_receiver decorator + HMAC verification
+ idempotency dedup. Routing en sinpapel_webhooks/urls.py propio (S14.4 D1).

Public API:
    from sinpapel_webhooks import webhook_receiver, __version__
"""
__version__ = "0.1.0"

# Lazy re-export to avoid Django app loading issues at module import time
def __getattr__(name: str):
    if name == "webhook_receiver":
        from .receivers.registry import webhook_receiver
        return webhook_receiver
    raise AttributeError(f"module 'sinpapel_webhooks' has no attribute {name!r}")


__all__ = ["__version__", "webhook_receiver"]
