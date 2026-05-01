"""Smoke E2E test (S14.1 / T5) — walking skeleton end-to-end.

Integration checkpoint: confirma que las piezas T1-T4 funcionan juntas:
sinpapel domain event → signal handler → transaction.on_commit → emit_event
→ InlineBackend.deliver_now → POST HMAC-firmado a URL.

Verifica:
- 3-package coexistence (sinpapel + sinpapel_drf + sinpapel_webhooks)
- Signal-driven outbound delivery
- HMAC verifiable round-trip con verify_signature
- WebhookDelivery status persistence
- Post-commit timing correcto
"""
from __future__ import annotations

import json

import pytest
import responses
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)
from sinpapel_webhooks.signing import verify_signature


@pytest.fixture(autouse=True)
def _use_inline_backend():
    """Walking skeleton tests asumen inline (sync POST). Outbox path test
    explícito en S14.2 T5 con override_settings + worker --once."""
    get_delivery_backend.cache_clear()
    with override_settings(SINPAPEL_WEBHOOKS_BACKEND="inline"):
        yield
    get_delivery_backend.cache_clear()


@pytest.mark.django_db(transaction=True)
@responses.activate
def test_walking_skeleton_outbound_workflow_transition():
    """E2E: Subscription + SeguimientoWorkflow → POST HMAC-firmado recibido."""
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow

    # Reset factory cache (en caso que tests previos cambiaron settings)
    get_delivery_backend.cache_clear()

    # --- Setup ----------------------------------------------------------

    user = User.objects.create_user(username="e2e-user", password="x")  # noqa: S106
    e_anterior = Estado.objects.create(nombre="EN_REVISION")
    e_nuevo = Estado.objects.create(nombre="FIRMADO")

    sub = WebhookSubscription.objects.create(
        name="e2e-consumer",
        url="https://consumer.test/webhook",
        events=["workflow.transition.completed"],
        secret="e2e-test-secret-32bytes-hex-aaa",
        active=True,
    )

    # Mock the consumer endpoint
    responses.add(
        responses.POST, "https://consumer.test/webhook",
        json={"acked": True}, status=200,
    )

    # Target genérico para el SeguimientoWorkflow GFK
    target = WebhookSubscription.objects.create(
        name="e2e-target", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    # --- Trigger event --------------------------------------------------

    SeguimientoWorkflow.objects.create(
        target_content_type=target_ct,
        target_object_id=target.pk,
        estado_anterior=e_anterior,
        estado_nuevo=e_nuevo,
        usuario_accion=user,
        comentarios="E2E walking skeleton test",
    )

    # --- Verify outbound POST -------------------------------------------

    assert len(responses.calls) == 1, f"Expected 1 POST, got {len(responses.calls)}"
    call = responses.calls[0]
    assert call.request.url == "https://consumer.test/webhook"

    # Headers presentes y correctos
    headers = call.request.headers
    assert headers["X-Sinpapel-Event-Type"] == "workflow.transition.completed"
    assert headers["X-Sinpapel-Webhook-Id"] == str(sub.id)
    assert headers["X-Sinpapel-Signature"].startswith("t=")
    assert ",v1=" in headers["X-Sinpapel-Signature"]
    assert headers["User-Agent"].startswith("sinpapel-webhooks/")
    assert headers["Content-Type"] == "application/json; charset=utf-8"

    # Body envelope structure (S14.2 D4)
    body_bytes = call.request.body
    if isinstance(body_bytes, str):
        body_bytes = body_bytes.encode()
    body = json.loads(body_bytes)
    assert body["event_type"] == "workflow.transition.completed"
    assert "event_id" in body
    assert "occurred_at" in body
    assert "metadata" in body
    # Domain data nested under "data" key
    assert body["data"]["estado_anterior"] == "EN_REVISION"
    assert body["data"]["estado_nuevo"] == "FIRMADO"
    assert body["data"]["comentarios"] == "E2E walking skeleton test"
    assert body["data"]["user_id"] == user.id

    # HMAC round-trip valida con el secret de la subscription
    verify_signature(
        body_bytes,
        headers["X-Sinpapel-Signature"],
        sub.secret,
        tolerance_seconds=300,
    )

    # --- Verify persistence ---------------------------------------------

    event = WebhookEvent.objects.get(event_type="workflow.transition.completed")
    assert event.payload["comentarios"] == "E2E walking skeleton test"

    # X-Sinpapel-Event-Id matches event.event_id
    assert headers["X-Sinpapel-Event-Id"] == str(event.event_id)

    delivery = WebhookDelivery.objects.get(subscription=sub, event=event)
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED
    assert delivery.attempts == 1
    assert delivery.last_response_status == 200


@pytest.mark.django_db(transaction=True)
@responses.activate
def test_walking_skeleton_consumer_returns_4xx_marks_failed():
    """E2E negativo: consumer 4xx → delivery.status="failed"."""
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow

    get_delivery_backend.cache_clear()

    user = User.objects.create_user(username="failure-user", password="x")  # noqa: S106
    e1 = Estado.objects.create(nombre="A")
    e2 = Estado.objects.create(nombre="B")

    sub = WebhookSubscription.objects.create(
        name="bad-consumer",
        url="https://bad.test/webhook",
        events=["workflow.transition.completed"],
        secret="s",
        active=True,
    )

    responses.add(
        responses.POST, "https://bad.test/webhook",
        json={"error": "not configured"}, status=404,
    )

    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    SeguimientoWorkflow.objects.create(
        target_content_type=target_ct, target_object_id=target.pk,
        estado_anterior=e1, estado_nuevo=e2, usuario_accion=user,
    )

    delivery = WebhookDelivery.objects.get(subscription=sub)
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.last_response_status == 404


@pytest.mark.django_db(transaction=True)
@responses.activate
def test_outbox_path_walking_skeleton_via_worker():
    """E2E S14.2: subscription + transition + worker --once → POST con envelope."""
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow

    # Override autouse fixture: este test usa outbox + worker
    get_delivery_backend.cache_clear()

    user = User.objects.create_user(username="outbox-e2e-user", password="x")  # noqa: S106
    e_anterior = Estado.objects.create(nombre="OUTBOX_ANTES")
    e_nuevo = Estado.objects.create(nombre="OUTBOX_DESPUES")

    sub = WebhookSubscription.objects.create(
        name="outbox-e2e-consumer",
        url="https://outbox.test/webhook",
        events=["workflow.transition.completed"],
        secret="outbox-e2e-secret-32bytes-aaa",
        active=True,
    )
    responses.add(responses.POST, "https://outbox.test/webhook", json={"ok": True}, status=200)

    target = WebhookSubscription.objects.create(
        name="outbox-target", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    with override_settings(SINPAPEL_WEBHOOKS_BACKEND="outbox"):
        get_delivery_backend.cache_clear()

        # Create transition (signal → emit_event → delivery pending; NO POST yet)
        SeguimientoWorkflow.objects.create(
            target_content_type=target_ct, target_object_id=target.pk,
            estado_anterior=e_anterior, estado_nuevo=e_nuevo,
            usuario_accion=user, comentarios="Outbox path E2E",
        )

        # No POST yet — outbox.enqueue is no-op
        assert len(responses.calls) == 0
        delivery = WebhookDelivery.objects.get(subscription=sub)
        assert delivery.status == WebhookDelivery.STATUS_PENDING

        # Run worker --once → drain pending + POST
        from io import StringIO
        from django.core.management import call_command
        call_command("sinpapel_webhooks_worker", once=True, stdout=StringIO())

    # POST received with envelope
    assert len(responses.calls) == 1
    call = responses.calls[0]
    body = json.loads(call.request.body if isinstance(call.request.body, bytes) else call.request.body.encode())
    assert body["event_type"] == "workflow.transition.completed"
    assert body["data"]["estado_nuevo"] == "OUTBOX_DESPUES"

    # HMAC valid round-trip
    verify_signature(
        call.request.body if isinstance(call.request.body, bytes) else call.request.body.encode(),
        call.request.headers["X-Sinpapel-Signature"],
        sub.secret,
    )

    # Delivery delivered
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED


@pytest.mark.django_db(transaction=True)
@responses.activate
def test_walking_skeleton_no_subscription_no_post():
    """Sin subscription matching → no POST + no delivery (event sí persistido)."""
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow

    get_delivery_backend.cache_clear()

    user = User.objects.create_user(username="no-sub-user", password="x")  # noqa: S106
    e1 = Estado.objects.create(nombre="A")
    e2 = Estado.objects.create(nombre="B")

    # NO subscription matching workflow.transition.completed

    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h",
        events=["unrelated.event"], secret="s",  # subscription no matching
    )
    target_ct = ContentType.objects.get_for_model(target)

    SeguimientoWorkflow.objects.create(
        target_content_type=target_ct, target_object_id=target.pk,
        estado_anterior=e1, estado_nuevo=e2, usuario_accion=user,
    )

    # Event persistido pero NO delivery
    assert WebhookEvent.objects.filter(event_type="workflow.transition.completed").count() == 1
    assert WebhookDelivery.objects.count() == 0

    # NO POST (responses no fue invocado)
    assert len(responses.calls) == 0
