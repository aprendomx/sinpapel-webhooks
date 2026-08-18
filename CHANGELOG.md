# Changelog

All notable changes to `sinpapel-webhooks` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] - 2026-08-18

### Changed

- Requiere `sinpapel>=0.7.1` (y `sinpapel-drf>=0.4.2` en el extra `drf`).
  Cambio relevante del core para este paquete: los side effects del motor
  ahora corren DESPUÉS del commit de la transacción de la transición — los
  webhooks emitidos desde side effects ya no pueden dispararse para
  transiciones que hacen rollback. Los receivers de signals
  (`predicate_failed`, `sla_breached`, etc.) no cambian.

### Changed

- **License:** MIT → GPL-3.0-or-later (aligns with `sinpapel` core license; ensures derivative-work compatibility).
- `requires-python` lowered from `>=3.13` to `>=3.10` to match `sinpapel` support matrix.
- `pyproject.toml` metadata refreshed: `license-files`, `setuptools>=77`, corrected project URLs (`aprendomx/sinpapel-webhooks`), and expanded Python/Django classifiers.
- Added `py.typed` marker for PEP 561 type-hint support.
- Added GPL-3.0 license headers to all source files.

(Next features: rate limiting + drf-spectacular polish + multi-tenancy candidates parking lot.)

## [0.2.1] - 2026-05-16

### Changed

- Refreshed `README.md` for v0.2.0 — install URLs now point to `aprendomx/sinpapel-webhooks.git@v0.2.x` (was legacy `creditos.git#subdirectory=` monorepo path); status header, Versioning section, and FAQ entries on Admin REST + secret rotation now describe the shipped feature instead of saying "deferred to v0.2".
- Added `README.es.md` — full Spanish parallel of the README covering all 13 sections, cross-linked from the English status header.

Docs-only patch; no API or behavior changes.

## [0.2.0] - 2026-05-16

**Event catalog expansion + Admin REST API.** Closes deferred S14.5 (subscription CRUD). Requires `sinpapel>=0.5.0` for the new signal-based events.

### Added — 7 new event types

Custom Django Signals declared in `sinpapel.signals` (loose coupling preserved — sinpapel core does NOT import sinpapel-webhooks):

- `workflow.predicate.failed` — fired by `WorkflowEngine._validar_predicados` when a `CondicionTransicion` rejects a transition.
- `workflow.predicate.configured` — `post_save(CondicionTransicion)` create/update.
- `workflow.transition.preview` — opt-in via `SINPAPEL_EMIT_PREVIEW_EVENTS=True`. Fires at the end of `WorkflowEngine.preview_transition`.
- `sla.configured` — `post_save(SLAConfiguracion)` create/update.
- `sla.breached` — fired by `SLAEngine._sla_vencida` when an instance exceeds `dias_maximos`.
- `sla.action.executed` — fired by `SLAEngine._ejecutar_accion` after dispatching a configured `_accion_*` handler.
- `workflow.metadata.captured` — consumer-emit pattern (call `emit_event("workflow.metadata.captured", payload, source=instance)` from your own post_save handler when consuming `MetadatosCapturables`).

### Added — Admin REST API (closes S14.5)

New subpackage `sinpapel_webhooks/admin_api/` (DRF viewsets + serializers). Optional install extra: `pip install sinpapel-webhooks[admin]` (depends on `djangorestframework>=3.14`). Defensive URL include — admin routes only mount when DRF is importable.

Routes under `/sinpapel/api/webhooks/admin/`:

- `subscriptions` — full CRUD + `POST /{id}/rotate-secret/` + `POST /{id}/test/` (synthetic delivery via InlineBackend).
- `deliveries` — read-only list/retrieve + `POST /{id}/retry/` + `POST /requeue-dead-letter/` (`{ids: [...]}` or `{all: true}`).
- `events` — read-only list (with `delivery_count`) + retrieve (embeds `deliveries` slim array).
- `inbound-events` — read-only list/retrieve.

Filters supported: `?status=`, `?subscription=`, `?since=` (deliveries); `?event_type=`, `?since=` (events); `?source=`, `?handler_status=`, `?since=` (inbound-events).

### Added — Settings

- `SINPAPEL_WEBHOOKS_ADMIN_PERMISSION` (default `"rest_framework.permissions.IsAdminUser"`) — dotted path to a DRF permission class; resolved at import time.
- `SINPAPEL_EMIT_PREVIEW_EVENTS` (sinpapel-side, default `False`) — toggles the `workflow.transition.preview` event emission.

### Added — Test infrastructure

- `tests/settings.py` + `tests/urls.py` so the suite runs standalone in this repo (previously required parent-project settings).

### Changed

- Subscription secrets are now masked on read (`***` + last 4 chars). Full value visible only in the create response and `rotate-secret` response (write-only on update).

### Compatibility

- Requires `sinpapel>=0.5.0` for the 4 signal-driven events. Older sinpapel versions still load (defensive import); only the 2 `post_save`-driven events will fire.

## [0.1.0] - 2026-05-01

**Epic E14 close.** Distributable via `pip install git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_webhooks`. Three-package coexistence (sinpapel core + sinpapel-drf + sinpapel-webhooks) verified.

5 stories delivered + 1 deferred (S14.5 admin endpoints → parking lot). Sub-epics E14a (Outbound 3 backends) + E14b (Inbound) + E14c (Adoption) all complete. 22 patterns nuevos (PAT-J-129..150). 2 ADRs (013 delivery port, 014 HMAC signing). 171 tests added. 99% coverage. Suite total 1212 verdes.

### Added — S14.6 (Adoption + epic polish)

- **README adoption guide** (`README.md`) — 13 secciones full adoption-focused (S12.8/S13.7 pattern):
  Installation / Quick Start / Settings / Outbound / Inbound / Backends / HMAC Verify (4 langs Python/JS/Ruby/Go) / Workers / Migrations / Troubleshooting / Reference / Versioning / FAQ.
- **Cross-component E2E test** (`tests/test_cross_component_e2e.py`) — PAT-E-539 integration checkpoint:
  - HMAC roundtrip outbound↔inbound (byte-exact compatibility verified)
  - Full outbox pipeline (signal → emit → worker → POST)
  - 3-backends Protocol conformance
- **Operational management commands:**
  - `manage.py sinpapel_webhooks_requeue_dead_letter [--all|--id N]`
  - `manage.py sinpapel_webhooks_test_subscription <subscription_id>` (synthetic transient payload)

### Notes — S14.5 deferred

S14.5 admin REST endpoints (subscription CRUD via sinpapel-drf) deferred a parking lot post-E14. Subscription/delivery management v0.1 vía Django admin auto-registered es sufficient para inicial release. Si demanda surge, future epic.

### Notes — S14.5 deferred (final)

S14.5 admin REST endpoints (subscription CRUD via sinpapel-drf) deferred a parking lot post-E14. Subscription/delivery management v0.1 vía Django admin auto-registered es sufficient para inicial release. Si demanda surge, future epic.

---

### Added — S14.4 (Inbound receiver framework)

- **`@webhook_receiver(source, event)` decorator** + `InboundReceiverRegistry` singleton para registrar handlers.
- **`ReceiverDispatcher`** con 9-step flow: HMAC verify + idempotency dedup + handler invoke + status persist.
- **`InboundWebhookView`** plain Django view (NOT DRF) + `csrf_exempt` decorator.
- **URL routing en `sinpapel_webhooks/urls.py` propio** (D1 architectural deviation: NOT en sinpapel_drf — preserves loose coupling).
  - `POST /sinpapel/api/webhooks/in/<source>/`
- **Auto-discovery** via `autodiscover_modules("webhooks")` en `apps.ready()`. Consumer apps con `<app>/webhooks.py` auto-load handlers.
- **Per-source secrets** vía `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` dict. Source missing → 401.
- **Status code matrix:**
  - 200: success (handler invoked) o duplicate (idempotency)
  - 400: missing required headers o invalid JSON
  - 401: HMAC invalid o unknown source
  - 404: no handler registered
  - 500: handler exception
- Reuse de S14.1: `verify_signature` + `InboundWebhookEvent` model + `WebhookSignatureError`.

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
