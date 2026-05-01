# sinpapel-webhooks

> **Event-driven HTTP communication for [sinpapel](../sinpapel/)** — outbound
> webhooks (signal-driven) + inbound receiver framework. HMAC-SHA256 signing
> Stripe-compatible, pluggable delivery backends (inline / outbox / celery),
> idempotency dedup. Production-ready sin broker dependency.

**Status:** v0.1.0 — distributable via `pip install git+ssh://...`. See [CHANGELOG](CHANGELOG.md).

---

## 1. Installation

```bash
# Core (incluye outbox backend default — DB-backed queue, no broker required)
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_webhooks"

# Con Celery distributed delivery (gated por extra)
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_webhooks[celery]"

# Con sinpapel-drf admin endpoints (futuro — S14.5 deferred)
# pip install "git+ssh://...sinpapel_webhooks[drf]"
```

**Requirements:** Python ≥3.13, Django ≥4.2, sinpapel ≥0.1.

---

## 2. Quick Start (5 min adoption)

### Step 1 — settings.py

```python
INSTALLED_APPS = [
    # ... django.contrib + simple_history + sinpapel + sinpapel_drf ...
    "sinpapel_webhooks",  # auto-discovers <app>/webhooks.py
]

# Outbound (default outbox = DB-backed queue, no broker)
SINPAPEL_WEBHOOKS_BACKEND = "outbox"

# Inbound (per-source secrets)
SINPAPEL_WEBHOOKS_INBOUND_SECRETS = {
    "baz": "<32-byte-hex-secret-from-baz-config>",
}
```

### Step 2 — urls.py

```python
from django.urls import include, path

urlpatterns = [
    # ... existing patterns ...
    path("sinpapel/api/webhooks/", include("sinpapel_webhooks.urls")),
]
```

### Step 3 — myapp/webhooks.py (auto-discovered)

```python
from sinpapel_webhooks import webhook_receiver


@webhook_receiver(source="baz", event="payment.confirmed")
def handle_baz_payment(payload, request):
    # Handle inbound webhook from BAZ
    return {"acked": True, "pago_id": payload["data"]["pago_id"]}
```

### Step 4 — Migrate + run worker

```bash
python manage.py migrate sinpapel_webhooks
python manage.py sinpapel_webhooks_worker  # daemon mode
```

### Step 5 — Create outbound subscription (Django admin or shell)

```python
from sinpapel_webhooks.models import WebhookSubscription

WebhookSubscription.objects.create(
    name="my-consumer",
    url="https://consumer.example.com/webhook",
    events=["workflow.transition.completed"],
    secret="<32-byte-hex>",
    active=True,
)
```

That's it. Outbound POSTs trigger automáticamente desde sinpapel signals
(workflow transitions, signatures, document changes). Inbound POSTs a
`/sinpapel/api/webhooks/in/baz/` invocan tu handler.

---

## 3. Settings Reference

| Setting | Default | Purpose |
|---------|---------|---------|
| `SINPAPEL_WEBHOOKS_BACKEND` | `"outbox"` | Delivery backend: `"inline"` / `"outbox"` / `"celery"` / dotted-path |
| `SINPAPEL_WEBHOOKS_REQUEST_TIMEOUT` | `10` | Seconds for HTTP POST timeout |
| `SINPAPEL_WEBHOOKS_TIMESTAMP_TOLERANCE` | `300` | Replay protection window (seconds) |
| `SINPAPEL_WEBHOOKS_MAX_ATTEMPTS` | `5` | Max retry attempts antes de dead_letter |
| `SINPAPEL_WEBHOOKS_RETRY_BACKOFF` | `[60, 300, 1800, 7200, 43200]` | Backoff seconds (1m/5m/30m/2h/12h) |
| `SINPAPEL_WEBHOOKS_DEAD_LETTER_AFTER_ATTEMPTS` | `True` | True → status="dead_letter"; False → "failed" |
| `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` | `{}` | Dict per-source secret: `{"source_name": "32-byte-hex"}` |

---

## 4. Outbound

Sinpapel-webhooks listens a 3 sinpapel domain events automatically:

| Event Type | Trigger |
|------------|---------|
| `workflow.transition.completed` | `SeguimientoWorkflow` created (transition exitosa) |
| `signature.completed` | `RegistroFirma` created |
| `document.uploaded` | `InstanciaDocumento` created |

### Subscription model

`WebhookSubscription`:
- `name`: human-readable label
- `url`: target POST URL
- `events`: JSON list of event types subscribed
- `secret`: HMAC-SHA256 secret (32-byte hex recommended)
- `active`: enable/disable
- `created_by`: User FK (audit)
- `history`: HistoricalRecords (django-simple-history audit trail)

### Payload envelope

```json
{
  "event_id": "01HXX5K8N3...",
  "event_type": "workflow.transition.completed",
  "occurred_at": "2026-05-01T14:22:33.123Z",
  "data": {
    "solicitud_id": 142,
    "estado_anterior": "EN_REVISION",
    "estado_nuevo": "FIRMADO",
    "user_id": 88,
    "comentarios": "Aprobado"
  },
  "metadata": {
    "sinpapel_version": "0.1.0",
    "webhooks_version": "0.1.0",
    "subscription_id": 5,
    "api_version": "2026-04-30"
  }
}
```

### Outbound headers

```
POST /your-webhook HTTP/1.1
Content-Type: application/json; charset=utf-8
User-Agent: sinpapel-webhooks/0.1.0
X-Sinpapel-Signature: t=1714492800,v1=<sha256-hex>
X-Sinpapel-Event-Id: 01HXX5K8N3...
X-Sinpapel-Event-Type: workflow.transition.completed
X-Sinpapel-Webhook-Id: 5
```

### Custom events

```python
from sinpapel_webhooks.emit import emit_event

emit_event(
    event_type="custom.invoice.paid",
    payload={"invoice_id": 142, "amount": 5000.0},
    source=invoice_instance,  # optional GFK
)
```

---

## 5. Inbound

### Decorator-based handler registration

```python
# myapp/webhooks.py — auto-discovered en startup vía autodiscover_modules
from sinpapel_webhooks import webhook_receiver


@webhook_receiver(source="baz", event="payment.confirmed")
def handle_baz_payment(payload, request):
    """payload es el envelope completo (event_id, event_type, occurred_at, data, metadata)."""
    pago_id = payload["data"]["pago_id"]
    monto = payload["data"]["monto"]
    # ... your logic
    return {"acked": True, "pago_id": pago_id}


@webhook_receiver(source="moneygram", event="dispersion.completed")
def handle_moneygram_dispersion(payload, request):
    """Returns None → defaults to {"acked": True}."""
    # ... your logic
```

### Inbound URL routing

```
POST /sinpapel/api/webhooks/in/<source>/
```

`<source>` matches `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` key.

### Inbound status codes

| Code | Reason |
|------|--------|
| 200 | Success (handler invoked) o duplicate (idempotency) |
| 400 | Missing required headers o invalid JSON body |
| 401 | HMAC signature invalid o unknown source |
| 404 | No handler registered para (source, event_type) |
| 500 | Handler raised exception |

### Idempotency

`InboundWebhookEvent.unique_together(source, event_id)` provee atomic dedup.
Si external service POSTea mismo event_id 2 veces, segunda recibe `200 {"acked": true, "duplicate": true}` sin re-invocar handler.

---

## 6. Backends — Choosing a delivery backend

| Backend | Use case | Pros | Cons |
|---------|----------|------|------|
| **`inline`** | Dev / smoke tests / very low volume | No infra; immediate delivery; debugging fácil | Bloquea Django request; no retry; pierde events on consumer downtime |
| **`outbox`** ⭐ default | Production default | No broker; at-least-once con retry; backpressure natural | Lag worker cycle (1-30s); requires worker process |
| **`celery`** | High volume / distributed | Distributed retry; horizontal scale; concurrency control | Requires Celery + broker (Redis/RabbitMQ) |

### Configuration

```python
# Inline (dev only)
SINPAPEL_WEBHOOKS_BACKEND = "inline"

# Outbox (default prod)
SINPAPEL_WEBHOOKS_BACKEND = "outbox"
# Run: python manage.py sinpapel_webhooks_worker

# Celery (high volume)
SINPAPEL_WEBHOOKS_BACKEND = "celery"
# Plus your existing Celery app config (broker, etc.)
```

### Custom backends

```python
# my_project/webhooks_backends.py
class MyBackend:
    name = "my_backend"
    def enqueue(self, delivery_id): ...
    def deliver_now(self, delivery_id): ...

# settings.py
SINPAPEL_WEBHOOKS_BACKEND = "my_project.webhooks_backends.MyBackend"
```

---

## 7. HMAC Verify (consumer-side)

Header format: `X-Sinpapel-Signature: t=<unix-ts>,v1=<sha256-hex>` (Stripe-compatible).

Algorithm: `HMAC-SHA256(secret, f"{timestamp}.".encode() + raw_body_bytes).hexdigest()`.

**Critical:** Use raw body bytes (NOT re-serialized JSON). Some frameworks parse + re-serialize body, which changes bytes and breaks HMAC.

### Test vector

```
payload: b'{"event":"test","data":{"x":1}}'
secret:  "demo-secret"
timestamp: 1714492800
expected: t=1714492800,v1=42740cbdf2a28e4c8c81742f20936d35a6895352d2395818f04a28d4e2030e11
```

### Python

```python
import hmac, hashlib, time

def verify_sinpapel_signature(payload: bytes, header: str, secret: str, *, tolerance: int = 300) -> bool:
    """Returns True if HMAC valid + timestamp within tolerance."""
    parts = dict(p.split("=", 1) for p in header.split(","))
    ts = int(parts["t"])
    if abs(time.time() - ts) > tolerance:
        return False  # Replay protection
    expected = hmac.new(
        secret.encode(),
        f"{ts}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

### JavaScript (Node.js)

```javascript
const crypto = require("crypto");

function verifySinpapelSignature(payload, header, secret, { tolerance = 300 } = {}) {
  // payload: Buffer | string (raw body, NOT re-serialized JSON)
  // header: "t=<ts>,v1=<hex>"
  const parts = Object.fromEntries(
    header.split(",").map(p => p.split("=", 2))
  );
  const ts = parseInt(parts.t, 10);
  if (Math.abs(Date.now() / 1000 - ts) > tolerance) return false;
  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${ts}.`)
    .update(payload)
    .digest("hex");
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(parts.v1),
  );
}
```

### Ruby

```ruby
require "openssl"

def verify_sinpapel_signature(payload, header, secret, tolerance: 300)
  parts = Hash[header.split(",").map { |p| p.split("=", 2) }]
  ts = parts["t"].to_i
  return false if (Time.now.to_i - ts).abs > tolerance
  expected = OpenSSL::HMAC.hexdigest("SHA256", secret, "#{ts}.#{payload}")
  Rack::Utils.secure_compare(expected, parts["v1"])
end
```

### Go

```go
import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "strconv"
    "strings"
    "time"
)

func VerifySinpapelSignature(payload []byte, header, secret string, tolerance int64) bool {
    parts := map[string]string{}
    for _, p := range strings.Split(header, ",") {
        kv := strings.SplitN(p, "=", 2)
        if len(kv) == 2 {
            parts[kv[0]] = kv[1]
        }
    }
    ts, err := strconv.ParseInt(parts["t"], 10, 64)
    if err != nil {
        return false
    }
    if abs(time.Now().Unix()-ts) > tolerance {
        return false
    }
    h := hmac.New(sha256.New, []byte(secret))
    h.Write([]byte(strconv.FormatInt(ts, 10) + "."))
    h.Write(payload)
    expected := hex.EncodeToString(h.Sum(nil))
    return hmac.Equal([]byte(expected), []byte(parts["v1"]))
}

func abs(x int64) int64 {
    if x < 0 { return -x }
    return x
}
```

---

## 8. Workers — Deployment

### Long-running daemon (production)

```bash
python manage.py sinpapel_webhooks_worker
```

### Cron / one-shot

```bash
python manage.py sinpapel_webhooks_worker --once
```

### Custom batch size + poll interval

```bash
python manage.py sinpapel_webhooks_worker --batch-size 100 --poll-interval 10
```

### systemd unit example

```ini
# /etc/systemd/system/sinpapel-webhooks-worker.service
[Unit]
Description=sinpapel-webhooks outbox worker
After=postgresql.service

[Service]
Type=simple
User=django
WorkingDirectory=/opt/myproject
Environment=DJANGO_SETTINGS_MODULE=myproject.settings
ExecStart=/opt/myproject/venv/bin/python manage.py sinpapel_webhooks_worker
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Operational commands

```bash
# Re-queue dead letter deliveries
python manage.py sinpapel_webhooks_requeue_dead_letter --all
python manage.py sinpapel_webhooks_requeue_dead_letter --id 142

# Test subscription URL + secret
python manage.py sinpapel_webhooks_test_subscription 5
```

---

## 9. Migrations

```bash
python manage.py migrate sinpapel_webhooks
```

Creates 4 tables:
- `sinpapel_webhooks_webhooksubscription` (+ history table for audit)
- `sinpapel_webhooks_webhookevent`
- `sinpapel_webhooks_webhookdelivery`
- `sinpapel_webhooks_inboundwebhookevent`

**3-package coexistence:** sinpapel + sinpapel_drf + sinpapel_webhooks correr en mismo Django process sin migration conflicts (verified vía 1200+ test suite).

**PostgreSQL recommended** para outbox backend multi-worker (`SELECT FOR UPDATE SKIP LOCKED`). SQLite fallback es single-worker only.

---

## 10. Troubleshooting

### Celery test config NOT propagated via Django settings

```python
# WRONG — Django override_settings NO propaga a Celery config
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_celery_backend(): ...

# CORRECT — set Celery config directly
@pytest.fixture(autouse=True)
def _eager_celery():
    from celery import current_app
    current_app.conf.task_always_eager = True
    current_app.conf.task_eager_propagates = True
    yield
```

### HMAC byte-exact requirement

```python
# WRONG — request.POST parses form-encoded; modifies bytes
body = request.POST.get("payload")

# WRONG — json.loads + re-serialize cambia bytes
body = json.dumps(json.loads(request.body))

# CORRECT — request.body returns raw bytes
body = request.body  # bytes
```

### autodiscover_modules edge cases

- Apps SIN `webhooks.py` → silently skipped (Django stdlib documented behavior)
- Apps con `webhooks.py` syntax error → ImportError raised at startup (loud failure)
- `webhooks.py` imports modules requiring DB → ensure migrations applied before test runner

### bulk_create NO dispara signals

```python
# WRONG — bulk_create bypasses post_save signals
SeguimientoWorkflow.objects.bulk_create([...])  # NO webhooks emitted

# CORRECT — use .save() iterativo if signals required
for s in seguimientos:
    s.save()  # signals fire normally
```

### Outbox queue grows unbounded

If consumer URL is permanently down, deliveries accumulate as `pending → failed` → retry → eventually `dead_letter`. Monitor:

```python
WebhookDelivery.objects.filter(status="dead_letter").count()
WebhookDelivery.objects.filter(status="failed").count()
```

Operational response: `python manage.py sinpapel_webhooks_requeue_dead_letter` after fixing consumer.

---

## 11. Reference

- **Architecture:** [`work/epics/e14-sinpapel-webhooks/design.md`](../work/epics/e14-sinpapel-webhooks/design.md)
- **ADR-013** (delivery port pluggable): [`dev/decisions/adr-013-webhook-delivery-pluggable-backend.md`](../dev/decisions/adr-013-webhook-delivery-pluggable-backend.md)
- **ADR-014** (HMAC signing scheme): [`dev/decisions/adr-014-webhook-signing-hmac-sha256.md`](../dev/decisions/adr-014-webhook-signing-hmac-sha256.md)

### Public API

```python
from sinpapel_webhooks import webhook_receiver, __version__
from sinpapel_webhooks.signing import compute_signature, verify_signature
from sinpapel_webhooks.emit import emit_event
from sinpapel_webhooks.delivery.ports import WebhookDeliveryBackend, DeliveryResult
from sinpapel_webhooks.exceptions import (
    SinpapelWebhooksError,
    WebhookSignatureError,
    WebhookDeliveryError,
    WebhookReceiverNotFound,
)
```

### Models

```python
from sinpapel_webhooks.models import (
    WebhookSubscription,    # outbound config
    WebhookEvent,           # canonical event log
    WebhookDelivery,        # delivery attempt log
    InboundWebhookEvent,    # idempotency dedup
)
```

---

## 12. Versioning

- **v0.1.0** (2026-05-01) — Initial release. Epic E14 close.
- **Lockstep:** `sinpapel_webhooks 0.1.x` requires `sinpapel >=0.1.0,<0.2`.
- **Future:** v0.2 may add admin endpoints (sinpapel-drf REST CRUD), secret rotation, mTLS, Kafka backend.

See [CHANGELOG.md](CHANGELOG.md) for full change history.

---

## 13. FAQ

### ¿Por qué `outbox` es default en lugar de `inline`?

Outbox no requiere broker (DB-backed queue) y provee at-least-once delivery con retry automático. Inline pierde events si consumer URL está down. Outbox = production-ready out-of-box.

### ¿Cómo migro de `inline` a `outbox`?

Single setting change + run worker:
```python
SINPAPEL_WEBHOOKS_BACKEND = "outbox"
```
```bash
python manage.py sinpapel_webhooks_worker
```

### ¿Cómo testeo Celery backend sin Redis broker?

```python
from celery import current_app
current_app.conf.task_always_eager = True  # NOT via Django settings
current_app.conf.task_eager_propagates = True
```

### ¿Por qué no DRF en inbound view?

Inbound es server-to-server JSON only — DRF parser/renderer overhead innecesario. Plain Django view + JsonResponse sufficient. Mantiene loose coupling con sinpapel_drf.

### ¿Cómo agregar custom event types?

`emit_event(event_type="custom.X", payload={...}, source=instance)` desde tu código. Subscriptions matching `events__contains="custom.X"` reciben.

### ¿Sinpapel-webhooks soporta WebSocket / SSE?

No en v0.1. Para push real-time usar Channels separado. Webhooks son HTTP POST callbacks event-driven.

### ¿Hay admin REST endpoints (subscription CRUD)?

No en v0.1 (S14.5 deferred). Usar Django admin auto-registered o shell. v0.2 puede agregar via sinpapel-drf integration.

### ¿Cómo rotar secrets?

v0.1: update `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` o `WebhookSubscription.secret` field. Restart Django process. v0.2 may add dual-secret overlap window.

---

**License:** MIT — see [LICENSE](LICENSE).
**Source:** https://github.com/jadrians/creditos/tree/main/sinpapel_webhooks
**Issues:** https://github.com/jadrians/creditos/issues
