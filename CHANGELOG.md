# Changelog

All notable changes to `sinpapel-webhooks` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — S14.3 (Celery adapter)

- **CeleryBackend** (`delivery/backends/celery.py`) — distributed delivery via Celery shared_task.
  - Gated por extra `[celery]` (`pip install sinpapel-webhooks[celery]`).
  - `enqueue` dispatcha task vía `_deliver_webhook_task.delay()`.
  - `deliver_now` reusa shared `executor.execute_delivery(allow_retry=True)` (manual retry path).
  - Lazy import + ImportError descriptive si celery no instalado.
- Factory short-name `"celery"` agregado.
- Tests con `current_app.conf.task_always_eager=True` (sync execution sin broker).

### Added — S14.2 (production outbound)

- **OutboxBackend** (`delivery/backends/outbox.py`) — DB-backed queue, default backend.
  - `enqueue` no-op (delivery persisted upstream by `emit_event`).
  - `deliver_now` con `allow_retry=True` semantics.
- **Worker management command** (`manage.py sinpapel_webhooks_worker`).
  - Args: `--once`, `--batch-size` (default 50), `--poll-interval` (default 5s).
  - PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` para multi-worker safety.
  - SQLite fallback: single-worker only (lock implícito).
  - Graceful shutdown via `KeyboardInterrupt`.
- **Retry policy** (`delivery/retry.py`).
  - Exponential backoff con jitter ±10%: 1m / 5m / 30m / 2h / 12h (configurable).
  - 4xx semantic differentiation: 400/401/403/404/410/422 → no retry; 408/429 → retry.
  - Max attempts → `dead_letter` (gated por `DEAD_LETTER_AFTER_ATTEMPTS=True` default).
- **`STATUS_DEAD_LETTER`** status (migration 0002).
- **Payload envelope** (D4 deferred desde S14.1):
  ```json
  {"event_id", "event_type", "occurred_at", "data", "metadata": {...}}
  ```
  Subscription_id varía per-delivery (D6).
- **Shared `_execute_delivery` executor** (refactor backward-compat de InlineBackend).
- **3 settings retry**: `MAX_ATTEMPTS=5`, `RETRY_BACKOFF=[60,300,1800,7200,43200]`, `DEAD_LETTER_AFTER_ATTEMPTS=True`.

### Changed

- **Default `SINPAPEL_WEBHOOKS_BACKEND` cambia de `"inline"` a `"outbox"`** (production-ready out-of-the-box, no broker dependency).

### Added — S14.1

- Paquete skeleton (`pyproject.toml`, `LICENSE`, `MANIFEST.in`).
- HMAC-SHA256 signing utilities (`compute_signature`, `verify_signature`)
  con header Stripe-compatible `t=<ts>,v1=<hex>` (ADR-014).
- 5 known-good HMAC test vectors hardcoded para regression protection.
- Exceptions module: `SinpapelWebhooksError`, `WebhookSignatureError`,
  `WebhookDeliveryError`, `WebhookReceiverNotFound`.
- AppConfig (`SinpapelWebhooksConfig`) con signal connections loose-coupled.
- 4 modelos: `WebhookSubscription` (history audit), `WebhookEvent` (UUID + GFK opcional),
  `WebhookDelivery` (4 status + 2 indexes), `InboundWebhookEvent` (idempotency unique).
- Migration 0001_initial.
- Delivery port (`WebhookDeliveryBackend` Protocol + `DeliveryResult` dataclass).
- `get_delivery_backend()` factory con `lru_cache` resetable.
- `InlineBackend` (sync, no retry — dev/smoke).
- `emit_event` helper con subscription filter + GFK populate.
- 3 signal handlers (SeguimientoWorkflow / RegistroFirma / InstanciaDocumento) con D2 snapshot pattern.

## [0.1.0] - TBD (E14 epic close)

- v0.1.0 inicial — outbound delivery + inbound receiver framework. Ver
  `work/epics/e14-sinpapel-webhooks/` para detalles del epic.
