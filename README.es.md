# sinpapel-webhooks

> **Comunicación HTTP event-driven para [sinpapel](../sinpapel/)** — webhooks
> salientes (disparados por signals) + framework de receptores entrantes.
> Firma HMAC-SHA256 compatible Stripe, backends de entrega intercambiables
> (inline / outbox / celery), deduplicación idempotente. Production-ready
> sin dependencia de broker.

**Estado:** v0.2.0 — catálogo de eventos expandido + Admin REST API. Ver [CHANGELOG](CHANGELOG.md) · [README in English](README.md).

---

## 1. Instalación

```bash
# Core (incluye outbox backend default — DB-backed queue, sin broker)
pip install "git+ssh://git@github.com/aprendomx/sinpapel-webhooks.git@v0.2.0"

# Con entrega distribuida vía Celery (gated por extra)
pip install "sinpapel-webhooks[celery] @ git+ssh://git@github.com/aprendomx/sinpapel-webhooks.git@v0.2.0"

# Con Admin REST API (Subscriptions CRUD + Deliveries/Events read — v0.2.0)
pip install "sinpapel-webhooks[admin] @ git+ssh://git@github.com/aprendomx/sinpapel-webhooks.git@v0.2.0"
```

**Requisitos:** Python ≥3.10, Django ≥5.0, sinpapel ≥0.5.0 (para el catálogo de eventos v0.2.0 completo; sinpapel previo sigue funcionando defensivamente — sólo los 2 eventos basados en `post_save` se emiten).

---

## 2. Quick Start (adopción en 5 minutos)

### Paso 1 — settings.py

```python
INSTALLED_APPS = [
    # ... django.contrib + simple_history + sinpapel + sinpapel_drf ...
    "sinpapel_webhooks",  # auto-descubre <app>/webhooks.py
]

# Salientes (default outbox = cola DB-backed, sin broker)
SINPAPEL_WEBHOOKS_BACKEND = "outbox"

# Entrantes (secretos por source)
SINPAPEL_WEBHOOKS_INBOUND_SECRETS = {
    "baz": "<secreto-hex-32-bytes-del-config-de-baz>",
}

# Opcional v0.2.0 — Admin REST
SINPAPEL_WEBHOOKS_ADMIN_PERMISSION = "rest_framework.permissions.IsAdminUser"
# Opcional v0.2.0 — Emitir eventos workflow.transition.preview (sinpapel-side)
SINPAPEL_EMIT_PREVIEW_EVENTS = False
```

### Paso 2 — urls.py

```python
from django.urls import include, path

urlpatterns = [
    # ... rutas existentes ...
    path("sinpapel/api/webhooks/", include("sinpapel_webhooks.urls")),
]
```

### Paso 3 — myapp/webhooks.py (auto-descubierto)

```python
from sinpapel_webhooks import webhook_receiver


@webhook_receiver(source="baz", event="payment.confirmed")
def handle_baz_payment(payload, request):
    # Maneja webhook entrante desde BAZ
    return {"acked": True, "pago_id": payload["data"]["pago_id"]}
```

### Paso 4 — Migrar + correr worker

```bash
python manage.py migrate sinpapel_webhooks
python manage.py sinpapel_webhooks_worker  # modo daemon
```

### Paso 5 — Crear subscription saliente (Django admin o shell)

```python
from sinpapel_webhooks.models import WebhookSubscription

WebhookSubscription.objects.create(
    name="mi-consumer",
    url="https://consumer.example.com/webhook",
    events=["workflow.transition.completed"],
    secret="<hex-32-bytes>",
    active=True,
)
```

Listo. Los POSTs salientes se disparan automáticamente desde las signals de sinpapel (transitions de workflow, firmas, cambios documentales). POSTs entrantes a `/sinpapel/api/webhooks/in/baz/` invocan tu handler.

---

## 3. Referencia de Settings

| Setting | Default | Propósito |
|---------|---------|-----------|
| `SINPAPEL_WEBHOOKS_BACKEND` | `"outbox"` | Backend de entrega: `"inline"` / `"outbox"` / `"celery"` / dotted-path |
| `SINPAPEL_WEBHOOKS_REQUEST_TIMEOUT` | `10` | Timeout (segundos) del POST HTTP |
| `SINPAPEL_WEBHOOKS_TIMESTAMP_TOLERANCE` | `300` | Ventana anti-replay (segundos) |
| `SINPAPEL_WEBHOOKS_MAX_ATTEMPTS` | `5` | Máximo de reintentos antes de dead_letter |
| `SINPAPEL_WEBHOOKS_RETRY_BACKOFF` | `[60, 300, 1800, 7200, 43200]` | Backoff en segundos (1m/5m/30m/2h/12h) |
| `SINPAPEL_WEBHOOKS_DEAD_LETTER_AFTER_ATTEMPTS` | `True` | True → status="dead_letter"; False → "failed" |
| `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` | `{}` | Dict secreto por source: `{"source_name": "hex-32-bytes"}` |
| `SINPAPEL_WEBHOOKS_ADMIN_PERMISSION` | `"rest_framework.permissions.IsAdminUser"` | Clase de permiso para Admin REST (dotted path) |
| `SINPAPEL_WEBHOOKS_ADMIN_PAGE_SIZE` | `50` | Tamaño de paginación de Admin REST |
| `SINPAPEL_EMIT_PREVIEW_EVENTS` | `False` | (sinpapel-side) Emitir `workflow.transition.preview` cuando se invoca preview_transition |

---

## 4. Salientes

### Catálogo de eventos (v0.2.0 — 10 tipos)

| event_type | Trigger | Requiere |
|---|---|---|
| `workflow.transition.completed` | `SeguimientoWorkflow` creado | sinpapel ≥ 0.1.0 |
| `signature.completed` | `RegistroFirma` creado | sinpapel ≥ 0.1.0 |
| `document.uploaded` | `InstanciaDocumento` creado | sinpapel ≥ 0.1.0 |
| `workflow.predicate.configured` | `CondicionTransicion` create/update | sinpapel ≥ 0.4.0 |
| `workflow.predicate.failed` | `WorkflowEngine` rechaza transition por un `CondicionTransicion` | sinpapel ≥ 0.5.0 (Signal custom) |
| `workflow.transition.preview` | `WorkflowEngine.preview_transition` (opt-in `SINPAPEL_EMIT_PREVIEW_EVENTS=True`) | sinpapel ≥ 0.5.0 |
| `sla.configured` | `SLAConfiguracion` create/update | sinpapel ≥ 0.4.0 |
| `sla.breached` | `SLAEngine` detecta instancia vencida (excede `dias_maximos`) | sinpapel ≥ 0.5.0 |
| `sla.action.executed` | `SLAEngine` dispara un handler `_accion_*` (notificar / escalar / rechazar / alertar) | sinpapel ≥ 0.5.0 |
| `workflow.metadata.captured` | Consumer-emit (llama `emit_event(...)` desde tu propio post_save sobre modelos con `MetadatosCapturables`) | — |

**Loose coupling:** los eventos que necesitan ≥0.5.0 usan Django Signals custom declaradas en `sinpapel.signals` (los receivers se auto-conectan en `apps.ready()`). Si la versión instalada de sinpapel no las expone, el `try: from sinpapel.signals import ...` defensivo permite que el paquete siga cargando — sólo los eventos basados en `post_save` se emiten.

### Modelo de subscription

`WebhookSubscription`:
- `name`: etiqueta legible
- `url`: URL POST destino
- `events`: lista JSON de event types suscritos
- `secret`: secreto HMAC-SHA256 (hex de 32 bytes recomendado)
- `active`: habilita/deshabilita
- `created_by`: User FK (audit)
- `history`: HistoricalRecords (audit trail vía django-simple-history)

### Payload envelope

```json
{
  "event_id": "01HXX5K8N3...",
  "event_type": "workflow.transition.completed",
  "occurred_at": "2026-05-16T14:22:33.123Z",
  "data": {
    "solicitud_id": 142,
    "estado_anterior": "EN_REVISION",
    "estado_nuevo": "FIRMADO",
    "user_id": 88,
    "comentarios": "Aprobado"
  },
  "metadata": {
    "sinpapel_version": "0.5.0",
    "webhooks_version": "0.2.0",
    "subscription_id": 5,
    "api_version": "2026-04-30"
  }
}
```

### Headers salientes

```
POST /your-webhook HTTP/1.1
Content-Type: application/json; charset=utf-8
User-Agent: sinpapel-webhooks/0.2.0
X-Sinpapel-Signature: t=1714492800,v1=<sha256-hex>
X-Sinpapel-Event-Id: 01HXX5K8N3...
X-Sinpapel-Event-Type: workflow.transition.completed
X-Sinpapel-Webhook-Id: 5
```

### Eventos custom

```python
from sinpapel_webhooks.emit import emit_event

emit_event(
    event_type="custom.invoice.paid",
    payload={"invoice_id": 142, "amount": 5000.0},
    source=invoice_instance,  # GFK opcional
)
```

---

## 5. Entrantes

POST a `/sinpapel/api/webhooks/in/<source>/` con headers:

```
X-Sinpapel-Signature: t=<unix-ts>,v1=<sha256-hex>
X-Sinpapel-Event-Id: <id-único-del-evento-externo>
X-Sinpapel-Event-Type: <tipo>
Content-Type: application/json
```

### Matriz de status codes

| Status | Significado |
|--------|-------------|
| 200 | Éxito (handler invocado) o duplicate (idempotencia) |
| 400 | Falta header requerido o JSON inválido |
| 401 | HMAC inválido o source desconocido |
| 404 | No hay handler registrado para (source, event_type) |
| 500 | El handler lanzó excepción |

### Registrar handlers

```python
from sinpapel_webhooks import webhook_receiver


@webhook_receiver(source="baz", event="payment.confirmed")
def handle_payment(payload, request):
    pago_id = payload["data"]["pago_id"]
    # ... lógica ...
    return {"acked": True, "pago_id": pago_id}
```

Auto-discovery: cualquier app en `INSTALLED_APPS` con un módulo `webhooks.py` se carga en `apps.ready()`.

---

## 6. Backends de entrega (ADR-013)

3 backends listos para usar:

| Backend | Cuándo usar | Trade-off |
|---------|-------------|-----------|
| `inline` | Tests, debugging | POST sincrónico en el request — bloquea response |
| `outbox` (default) | Producción sin broker | DB-backed queue + worker mgmt command; SKIP LOCKED en Postgres |
| `celery` | Producción con broker existente | Distribución vía `shared_task` — requiere extra `[celery]` |

Cambio de backend = un setting:

```python
SINPAPEL_WEBHOOKS_BACKEND = "celery"  # o "inline" / "outbox" / "myapp.backend.Custom"
```

### Worker (backend outbox)

```bash
python manage.py sinpapel_webhooks_worker --batch-size 50 --poll-interval 5
# Flags: --once (procesa una tanda y sale), --batch-size, --poll-interval (segs)
```

---

## 7. Verificar HMAC (snippets receiver-side)

### Python

```python
import hmac, hashlib

def verify(body: bytes, header: str, secret: str, tolerance: int = 300) -> bool:
    parts = dict(p.split("=") for p in header.split(","))
    ts, signature = int(parts["t"]), parts["v1"]
    import time
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Node.js

```javascript
const crypto = require("crypto");

function verify(body, header, secret, tolerance = 300) {
    const parts = Object.fromEntries(header.split(",").map(p => p.split("=")));
    const ts = parseInt(parts.t);
    if (Math.abs(Date.now() / 1000 - ts) > tolerance) return false;
    const expected = crypto.createHmac("sha256", secret)
        .update(`${ts}.` + body)
        .digest("hex");
    return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(parts.v1));
}
```

### Ruby

```ruby
require "openssl"

def verify(body, header, secret, tolerance = 300)
    parts = header.split(",").map { |p| p.split("=") }.to_h
    ts = parts["t"].to_i
    return false if (Time.now.to_i - ts).abs > tolerance
    expected = OpenSSL::HMAC.hexdigest("SHA256", secret, "#{ts}." + body)
    Rack::Utils.secure_compare(expected, parts["v1"])
end
```

### Go

```go
import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "strings"
    "time"
)

func verify(body []byte, header, secret string, tolerance int64) bool {
    parts := map[string]string{}
    for _, p := range strings.Split(header, ",") {
        kv := strings.SplitN(p, "=", 2)
        parts[kv[0]] = kv[1]
    }
    var ts int64
    fmt.Sscanf(parts["t"], "%d", &ts)
    if abs(time.Now().Unix()-ts) > tolerance { return false }
    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write([]byte(fmt.Sprintf("%d.", ts)))
    mac.Write(body)
    return hmac.Equal([]byte(hex.EncodeToString(mac.Sum(nil))), []byte(parts["v1"]))
}
```

---

## 8. Admin REST API (v0.2.0)

Instala el extra:

```bash
pip install sinpapel-webhooks[admin]
```

Monta los URLs (mismo `include` que el endpoint entrante):

```python
urlpatterns = [
    path("sinpapel/api/webhooks/", include("sinpapel_webhooks.urls")),
]
```

Rutas (todas bajo `/sinpapel/api/webhooks/admin/`):

| Verbo + Path | Propósito |
|---|---|
| `GET    /admin/subscriptions/` | Lista subscriptions (paginada) |
| `POST   /admin/subscriptions/` | Crea — la response devuelve `secret` en plaintext UNA vez |
| `GET    /admin/subscriptions/{id}/` | Retrieve — `secret` enmascarado (`***` + últimos 4) |
| `PATCH  /admin/subscriptions/{id}/` | Update — `secret` es read-only aquí |
| `DELETE /admin/subscriptions/{id}/` | Delete |
| `POST   /admin/subscriptions/{id}/rotate-secret/` | Rota el secret — response devuelve el nuevo valor una vez |
| `POST   /admin/subscriptions/{id}/test/` | Envía un delivery sintético vía `InlineBackend` |
| `GET    /admin/deliveries/` | Lista deliveries — filtros: `?status=`, `?subscription=`, `?since=` |
| `GET    /admin/deliveries/{id}/` | Retrieve delivery |
| `POST   /admin/deliveries/{id}/retry/` | Re-encola un delivery (resetea a pending) |
| `POST   /admin/deliveries/requeue-dead-letter/` | Body `{ids: [...]}` o `{all: true}` |
| `GET    /admin/events/` | Lista events con `delivery_count` |
| `GET    /admin/events/{id}/` | Retrieve event con deliveries embebidas |
| `GET    /admin/inbound-events/` | Lista log dedup entrante — filtros: `?source=`, `?handler_status=`, `?since=` |
| `GET    /admin/inbound-events/{id}/` | Retrieve inbound event |

### Autenticación

Permiso default: `rest_framework.permissions.IsAdminUser`. Sobrescribe con el setting:

```python
SINPAPEL_WEBHOOKS_ADMIN_PERMISSION = "miapp.permissions.IsOpsTeam"
```

Resuelto vía `import_string` al cargar el módulo; un dotted path inválido lanza `ImproperlyConfigured` al startup.

### Ejemplos

```bash
# Crear subscription (la response es la ÚNICA vez que el secret completo es visible)
curl -X POST https://api.example.com/sinpapel/api/webhooks/admin/subscriptions/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"ops","url":"https://ops.example.com/hook","events":["workflow.transition.completed"],"secret":"<hex-32-bytes>"}'

# Rotar el secret
curl -X POST https://api.example.com/sinpapel/api/webhooks/admin/subscriptions/5/rotate-secret/ \
  -H "Authorization: Token <admin-token>"

# Re-encolar todos los dead-letter
curl -X POST https://api.example.com/sinpapel/api/webhooks/admin/deliveries/requeue-dead-letter/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"all": true}'
```

---

## 9. Comandos de management

| Comando | Propósito |
|---------|-----------|
| `sinpapel_webhooks_worker` | Worker outbox (procesa deliveries pending) |
| `sinpapel_webhooks_test_subscription <id>` | Envía payload sintético a una subscription (debug URL+secret) |
| `sinpapel_webhooks_requeue_dead_letter [--all | --id N]` | Re-encola deliveries dead-letter (alternativa CLI al endpoint REST) |

---

## 10. Troubleshooting

**No llegan eventos a mi URL.**
1. ¿`WebhookSubscription.active = True`?
2. ¿El `event_type` está en la lista `events`?
3. Si `SINPAPEL_WEBHOOKS_BACKEND = "outbox"`: ¿corre el worker?
4. Revisa `WebhookDelivery.last_error` para mensajes del POST.

**401 en mis endpoints entrantes.**
- HMAC fail. Verifica que el secret en `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` coincide con el que firma el emisor, y que el clock skew está dentro de `SINPAPEL_WEBHOOKS_TIMESTAMP_TOLERANCE`.

**Los eventos v0.5+ no se emiten.**
- Verifica `sinpapel >=0.5.0` instalado: `pip show sinpapel | grep Version`. Si tienes una versión menor, sólo los 2 eventos `post_save` (`predicate.configured`, `sla.configured`) se emiten — los 4 signal-driven (`predicate.failed`, `sla.breached`, `sla.action.executed`, `transition.preview`) requieren los Signals custom de sinpapel ≥0.5.0.

**Admin REST devuelve 404.**
- Verifica que el extra `[admin]` está instalado: `pip show djangorestframework`. El URL include se monta defensivamente — si DRF no está disponible, las rutas admin no existen.

---

## 11. Referencia rápida

### Imports públicos

```python
from sinpapel_webhooks import webhook_receiver, __version__
from sinpapel_webhooks.emit import emit_event
from sinpapel_webhooks.models import (
    WebhookSubscription,
    WebhookEvent,
    WebhookDelivery,
    InboundWebhookEvent,
)
from sinpapel_webhooks.signing import verify_signature  # raises WebhookSignatureError
```

### Receiver framework

- `@webhook_receiver(source, event)` — decorator
- `InboundReceiverRegistry.get(source, event)` — lookup

### Delivery factory

- `get_delivery_backend()` — retorna instancia del backend configurado (cacheado con `lru_cache`)

---

## 12. Versionado

- **v0.2.0** (2026-05-16) — Catálogo de eventos expandido (7 nuevos event types) + Admin REST API (Subscriptions CRUD + Deliveries read/retry + Events/InboundEvents read). Requiere `sinpapel >=0.5.0` para los 4 eventos signal-driven; sinpapel previo sigue cargando (defensive import) con los 2 eventos `post_save` funcionales.
- **v0.1.0** (2026-05-01) — Release inicial. Cierre Epic E14.
- **Lockstep:** `sinpapel_webhooks 0.2.x` requiere `sinpapel >=0.5.0,<0.6` para feature set completo (degrada gracefully en sinpapel previo).
- **Próximo:** v0.3 puede añadir rate limiting, schema OpenAPI vía drf-spectacular, multi-tenancy, mTLS, backend Kafka.

Ver [CHANGELOG.md](CHANGELOG.md) para historial completo.

---

## 13. FAQ

### ¿Por qué `outbox` es default en lugar de `inline`?

Outbox no requiere broker (DB-backed queue) y provee at-least-once delivery con retry automático. Inline pierde events si la URL consumer está down. Outbox = production-ready out-of-box.

### ¿Cómo migro de `inline` a `outbox`?

Un setting + corre el worker:
```python
SINPAPEL_WEBHOOKS_BACKEND = "outbox"
```
```bash
python manage.py sinpapel_webhooks_worker
```

### ¿Cómo testeo el backend Celery sin un broker Redis?

```python
from celery import current_app
current_app.conf.task_always_eager = True  # NO vía Django settings
current_app.conf.task_eager_propagates = True
```

### ¿Por qué no DRF en la vista entrante?

Inbound es server-to-server JSON only — el overhead de parser/renderer DRF es innecesario. Plain Django view + JsonResponse alcanza. Mantiene loose coupling con sinpapel_drf.

### ¿Cómo agregar event types custom?

`emit_event(event_type="custom.X", payload={...}, source=instance)` desde tu código. Las subscriptions matching `events__contains="custom.X"` reciben.

### ¿Sinpapel-webhooks soporta WebSocket / SSE?

No. Para push real-time usar Channels separado. Webhooks son callbacks HTTP POST event-driven.

### ¿Hay endpoints admin REST (subscription CRUD)?

**Sí, desde v0.2.0.** Instala con `pip install sinpapel-webhooks[admin]` y monta el include — automáticamente expone `/sinpapel/api/webhooks/admin/subscriptions/` (CRUD + rotate-secret + test), `/admin/deliveries/` (read + retry + requeue-dead-letter), `/admin/events/`, `/admin/inbound-events/`. Permiso default `IsAdminUser`; override vía setting `SINPAPEL_WEBHOOKS_ADMIN_PERMISSION`.

### ¿Cómo rotar secrets?

**Salientes (v0.2.0+):** `POST /sinpapel/api/webhooks/admin/subscriptions/{id}/rotate-secret/` — el servidor genera un hex de 32 bytes nuevo y la response devuelve el plaintext (única vez). El campo `secret` en GET/PATCH viene enmascarado (`***` + últimos 4).

**Entrantes:** actualiza `SINPAPEL_WEBHOOKS_INBOUND_SECRETS` dict y reinicia el proceso Django. Una ventana dual-secret de overlap queda en backlog.

---

**Licencia:** GPL-3.0-or-later — ver [LICENSE](LICENSE).
**Fuente:** https://github.com/aprendomx/sinpapel-webhooks
**Issues:** https://github.com/aprendomx/sinpapel-webhooks/issues
