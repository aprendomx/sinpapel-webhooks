"""Cross-component E2E tests (S14.6 / T1, PAT-E-539 integration checkpoint).

Verifies seam joints entre stories S14.1-S14.4:
- HMAC byte-exact compatibility outbound (compute) ↔ inbound (verify)
- Full outbox pipeline (signal → emit → worker → POST)
- 3-backends Protocol conformance (inline + outbox + celery)

CRITICAL: HMAC roundtrip test confirma que sinpapel_webhooks puede
funcionar self-loop (outbound a sí mismo via inbound). Si rompe →
arquitectura epic comprometida.
"""
from __future__ import annotations

import json
import time
from io import StringIO

import pytest
import responses
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client, override_settings

from sinpapel_webhooks.delivery.backends.celery import CeleryBackend
from sinpapel_webhooks.delivery.backends.inline import InlineBackend
from sinpapel_webhooks.delivery.backends.outbox import OutboxBackend
from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.delivery.ports import WebhookDeliveryBackend
from sinpapel_webhooks.emit import emit_event
from sinpapel_webhooks.models import (
    InboundWebhookEvent,
    WebhookDelivery,
    WebhookSubscription,
)
from sinpapel_webhooks.receivers.registry import (
    InboundReceiverRegistry,
    webhook_receiver,
)


SHARED_SECRET = "cross-component-e2e-secret-32bytes-aaa"


@pytest.fixture(autouse=True)
def _clear_registry():
    InboundReceiverRegistry.clear()
    yield
    InboundReceiverRegistry.clear()


# --- HMAC roundtrip (CRITICAL) -------------------------------------------


@pytest.mark.django_db(transaction=True)
@override_settings(
    SINPAPEL_WEBHOOKS_BACKEND="inline",
    SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"self_test": SHARED_SECRET},
)
@responses.activate
def test_outbound_hmac_compatible_with_inbound_verify():
    """PAT-E-539: HMAC outbound compute byte-exact compatible con inbound verify.

    Same secret usado para outbound subscription Y inbound source. Replay
    captured POST como inbound — verify_signature debe pass.
    """
    get_delivery_backend.cache_clear()

    # Setup inbound handler
    @webhook_receiver(source="self_test", event="self.test")
    def echo_handler(payload, request):
        return {"echoed": payload, "source": "self_test"}

    # Outbound subscription con SAME secret que inbound
    sub = WebhookSubscription.objects.create(
        name="self-test-outbound",
        url="https://capture.test/hook",
        events=["self.test"],
        secret=SHARED_SECRET,
        active=True,
    )
    responses.add(responses.POST, "https://capture.test/hook", status=200)

    # Trigger outbound via emit_event (InlineBackend → POST sync)
    emit_event("self.test", {"message": "roundtrip", "n": 42})

    # Capture outbound request
    assert len(responses.calls) == 1
    captured = responses.calls[0].request
    captured_body = captured.body if isinstance(captured.body, bytes) else captured.body.encode()
    captured_signature = captured.headers["X-Sinpapel-Signature"]
    captured_event_id = captured.headers["X-Sinpapel-Event-Id"]

    # Replay as inbound — same body, same signature, same secret
    client = Client()
    response = client.post(
        "/sinpapel/api/webhooks/in/self_test/",
        data=captured_body,
        content_type="application/json",
        headers={
            "X-Sinpapel-Signature": captured_signature,
            "X-Sinpapel-Event-Id": captured_event_id,
            "X-Sinpapel-Event-Type": "self.test",
        },
    )

    # CRITICAL ASSERTION: HMAC outbound compute matches inbound verify
    assert response.status_code == 200, (
        f"HMAC byte-exact incompatibility detected: outbound→inbound roundtrip failed. "
        f"Response: {response.json()}"
    )
    # Handler receives full envelope (event_id + event_type + data + metadata)
    body = response.json()
    echoed_envelope = body["echoed"]
    assert echoed_envelope["event_type"] == "self.test"
    # Original payload nested bajo "data" key (D4 envelope structure)
    assert echoed_envelope["data"]["message"] == "roundtrip"
    assert echoed_envelope["data"]["n"] == 42

    # Inbound event persisted
    assert InboundWebhookEvent.objects.filter(
        source="self_test", event_id=captured_event_id,
    ).exists()


# --- Full outbox pipeline ------------------------------------------------


@pytest.mark.django_db(transaction=True)
@override_settings(SINPAPEL_WEBHOOKS_BACKEND="outbox")
@responses.activate
def test_full_outbox_pipeline_via_worker():
    """Pipeline complete: SeguimientoWorkflow create → signal → emit_event
    → WebhookDelivery pending → worker --once → POST + delivered.
    """
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow

    get_delivery_backend.cache_clear()

    user = User.objects.create_user(username="pipeline-user", password="x")  # noqa: S106
    e_anterior = Estado.objects.create(nombre="PIPELINE_ANTES")
    e_nuevo = Estado.objects.create(nombre="PIPELINE_DESPUES")

    sub = WebhookSubscription.objects.create(
        name="pipeline-sub",
        url="https://pipeline.test/hook",
        events=["workflow.transition.completed"],
        secret="pipeline-secret-32bytes-aaa-bbb",
        active=True,
    )
    responses.add(responses.POST, "https://pipeline.test/hook", status=200)

    target = WebhookSubscription.objects.create(
        name="target", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    # Trigger signal — creates pending delivery (outbox enqueue is no-op)
    SeguimientoWorkflow.objects.create(
        target_content_type=target_ct, target_object_id=target.pk,
        estado_anterior=e_anterior, estado_nuevo=e_nuevo,
        usuario_accion=user, comentarios="Pipeline E2E",
    )

    # Pre-worker: delivery pending, NO POST yet
    assert len(responses.calls) == 0
    delivery = WebhookDelivery.objects.get(subscription=sub)
    assert delivery.status == WebhookDelivery.STATUS_PENDING

    # Run worker --once → drain pending → POST
    call_command("sinpapel_webhooks_worker", once=True, stdout=StringIO())

    # Post-worker: POST sent, delivery delivered
    assert len(responses.calls) == 1
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED


# --- 3-backends Protocol conformance --------------------------------------


def test_three_backends_protocol_conformance():
    """Los 3 backends del delivery port pluggable (ADR-013) implementan Protocol."""
    inline = InlineBackend()
    outbox = OutboxBackend()
    celery = CeleryBackend()

    assert isinstance(inline, WebhookDeliveryBackend)
    assert isinstance(outbox, WebhookDeliveryBackend)
    assert isinstance(celery, WebhookDeliveryBackend)

    assert inline.name == "inline"
    assert outbox.name == "outbox"
    assert celery.name == "celery"

    # Factory resuelve los 3 short-names
    for short_name, expected_class in [
        ("inline", InlineBackend),
        ("outbox", OutboxBackend),
        ("celery", CeleryBackend),
    ]:
        get_delivery_backend.cache_clear()
        with override_settings(SINPAPEL_WEBHOOKS_BACKEND=short_name):
            backend = get_delivery_backend()
            assert isinstance(backend, expected_class), (
                f"Factory NO resuelve '{short_name}' a {expected_class.__name__}"
            )


# --- workflow.predicate.configured HMAC roundtrip (v0.2.0) ----------------


@pytest.mark.django_db(transaction=True)
@responses.activate
def test_predicate_configured_emits_hmac_signed_delivery_e2e(settings):
    """post_save CondicionTransicion → HMAC-signed POST verifiable on receiver side."""
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo
    from sinpapel.models.predicates import CondicionTransicion

    from sinpapel_webhooks.signing import verify_signature

    settings.SINPAPEL_WEBHOOKS_BACKEND = "inline"
    get_delivery_backend.cache_clear()
    responses.add(
        responses.POST, "https://hook.test/predicate",
        json={"acked": True}, status=200,
    )
    sub = WebhookSubscription.objects.create(
        name="hook", url="https://hook.test/predicate",
        events=["workflow.predicate.configured"],
        secret="topsecret-32-bytes-of-fun",
        active=True,
    )

    e_a = Estado.objects.create(nombre="A-E2E")
    e_b = Estado.objects.create(nombre="B-E2E")
    flujo = VersionFlujo.objects.create(nombre="F-E2E-PC", activo=True)
    config_t = ConfiguracionTransicion.objects.create(
        flujo=flujo, estado_origen=e_a, estado_destino=e_b,
    )
    CondicionTransicion.objects.create(
        transicion=config_t, tipo="json_logic",
        configuracion={"rule": {"==": [1, 1]}}, mensaje_error="ok", activo=True,
    )

    assert len(responses.calls) == 1
    call = responses.calls[0]
    sig_header = call.request.headers.get("X-Sinpapel-Signature", "")
    body = call.request.body
    # Verify HMAC roundtrip on the receiver side.
    verify_signature(body if isinstance(body, bytes) else body.encode(), sig_header, sub.secret)
