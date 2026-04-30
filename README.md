# sinpapel-webhooks

> Event-driven HTTP communication para [sinpapel](../sinpapel/) — outbound +
> inbound webhooks con HMAC-SHA256 signing, pluggable delivery backends, e
> idempotency dedup.

**⚠️ Work in progress (E14, S14.1+).** Este README es placeholder skeleton.
La guía de adopción completa (13 secciones siguiendo S12.8/S13.7 pattern)
llega en S14.6.

## Status (post-S14.1)

| Componente | Status |
|------------|:------:|
| Paquete instalable (`pyproject.toml`) | ☐ |
| Models persistentes (Subscription/Event/Delivery/InboundEvent) | ☐ |
| HMAC signing utilities (compute/verify) | ☐ |
| Signal hooks (loose coupling con sinpapel core) | ☐ |
| Delivery port + InlineBackend | ☐ |
| Outbox backend + worker | _S14.2_ |
| Celery backend (gated) | _S14.3_ |
| Inbound receiver framework | _S14.4_ |
| Admin endpoints (sinpapel-drf) | _S14.5_ |
| README adoption + smoke E2E | _S14.6_ |

## Installation (preview)

```bash
# Pre-1.0 vía git URL
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_webhooks"

# Con extras
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_webhooks[celery]"
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_webhooks[drf]"
```

## References

- Epic design: [`../work/epics/e14-sinpapel-webhooks/design.md`](../work/epics/e14-sinpapel-webhooks/design.md)
- ADR-013 (delivery port): [`../dev/decisions/adr-013-webhook-delivery-pluggable-backend.md`](../dev/decisions/adr-013-webhook-delivery-pluggable-backend.md)
- ADR-014 (HMAC signing): [`../dev/decisions/adr-014-webhook-signing-hmac-sha256.md`](../dev/decisions/adr-014-webhook-signing-hmac-sha256.md)
