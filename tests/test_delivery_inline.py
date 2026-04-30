"""InlineBackend tests (S14.1 / T3).

POST mocking via responses library. Verifica:
- Headers X-Sinpapel-* presentes y correctos
- Body es JSON serialization del event payload
- HMAC signature verifiable round-trip
- Status persistence: 2xx → delivered, 4xx/5xx → failed
- Timeout / ConnectionError handling
- attempts counter increment
"""
from __future__ import annotations

import json
import re

import pytest
import requests
import responses
from django.test import override_settings

from sinpapel_webhooks.delivery.backends.inline import InlineBackend
from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.delivery.ports import (
    DeliveryResult,
    WebhookDeliveryBackend,
)
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)
from sinpapel_webhooks.signing import verify_signature


# --- Fixtures -------------------------------------------------------------


@pytest.fixture
def subscription(db):
    return WebhookSubscription.objects.create(
        name="test-sub",
        url="https://consumer.test/hook",
        events=["workflow.transition.completed"],
        secret="test-hmac-secret-32bytes-hex-aaa",
    )


@pytest.fixture
def event(db):
    return WebhookEvent.objects.create(
        event_type="workflow.transition.completed",
        payload={
            "solicitud_id": 142,
            "estado_anterior": "EN_REVISION",
            "estado_nuevo": "FIRMADO",
        },
    )


@pytest.fixture
def delivery(subscription, event):
    return WebhookDelivery.objects.create(
        subscription=subscription, event=event,
    )


# --- Protocol conformance -------------------------------------------------


def test_inline_backend_implements_protocol():
    backend = InlineBackend()
    assert isinstance(backend, WebhookDeliveryBackend)
    assert backend.name == "inline"


# --- Factory --------------------------------------------------------------


@override_settings(SINPAPEL_WEBHOOKS_BACKEND="inline")
def test_factory_resolves_inline_short_name():
    get_delivery_backend.cache_clear()
    backend = get_delivery_backend()
    assert isinstance(backend, InlineBackend)


@override_settings(SINPAPEL_WEBHOOKS_BACKEND="sinpapel_webhooks.delivery.backends.inline.InlineBackend")
def test_factory_resolves_dotted_path():
    get_delivery_backend.cache_clear()
    backend = get_delivery_backend()
    assert isinstance(backend, InlineBackend)


@override_settings(SINPAPEL_WEBHOOKS_BACKEND="invalid-no-dots")
def test_factory_raises_on_invalid_setting():
    from django.core.exceptions import ImproperlyConfigured
    get_delivery_backend.cache_clear()
    with pytest.raises(ImproperlyConfigured, match="must be a short-name"):
        get_delivery_backend()


@override_settings(SINPAPEL_WEBHOOKS_BACKEND="nonexistent.module.Backend")
def test_factory_raises_on_unimportable_backend():
    from django.core.exceptions import ImproperlyConfigured
    get_delivery_backend.cache_clear()
    with pytest.raises(ImproperlyConfigured, match="Could not import"):
        get_delivery_backend()


# --- 2xx success path -----------------------------------------------------


@responses.activate
def test_inline_post_success_200(delivery, subscription):
    responses.add(
        responses.POST, "https://consumer.test/hook",
        json={"ok": True}, status=200,
    )

    backend = InlineBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is True
    assert result.status_code == 200

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED
    assert delivery.attempts == 1
    assert delivery.last_response_status == 200
    assert delivery.last_attempt_at is not None


@responses.activate
def test_inline_post_success_201(delivery, subscription):
    responses.add(responses.POST, "https://consumer.test/hook", status=201)
    backend = InlineBackend()
    result = backend.deliver_now(delivery.id)
    assert result.success is True
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED


# --- Headers and HMAC verification ----------------------------------------


@responses.activate
def test_inline_post_includes_required_headers(delivery, subscription, event):
    responses.add(responses.POST, "https://consumer.test/hook", status=200)
    backend = InlineBackend()
    backend.deliver_now(delivery.id)

    call = responses.calls[0]
    headers = call.request.headers

    assert headers["X-Sinpapel-Event-Type"] == "workflow.transition.completed"
    assert headers["X-Sinpapel-Event-Id"] == str(event.event_id)
    assert headers["X-Sinpapel-Webhook-Id"] == str(subscription.id)
    assert headers["X-Sinpapel-Signature"].startswith("t=")
    assert ",v1=" in headers["X-Sinpapel-Signature"]
    assert headers["User-Agent"].startswith("sinpapel-webhooks/")
    assert headers["Content-Type"] == "application/json; charset=utf-8"


@responses.activate
def test_inline_post_signature_verifies_round_trip(delivery, subscription):
    responses.add(responses.POST, "https://consumer.test/hook", status=200)
    backend = InlineBackend()
    backend.deliver_now(delivery.id)

    call = responses.calls[0]
    body_bytes = call.request.body
    if isinstance(body_bytes, str):
        body_bytes = body_bytes.encode()

    # Round-trip: el HMAC enviado debe verificar con el secret de la subscription
    verify_signature(
        body_bytes,
        call.request.headers["X-Sinpapel-Signature"],
        subscription.secret,
        tolerance_seconds=300,
    )


@responses.activate
def test_inline_post_body_contains_event_payload(delivery, event):
    responses.add(responses.POST, "https://consumer.test/hook", status=200)
    backend = InlineBackend()
    backend.deliver_now(delivery.id)

    call = responses.calls[0]
    body_bytes = call.request.body
    if isinstance(body_bytes, str):
        body_bytes = body_bytes.encode()
    body = json.loads(body_bytes)

    # S14.1 simple payload — emit_event en T4 enriquecerá con envelope completo
    assert body == event.payload


# --- 4xx/5xx failure paths ------------------------------------------------


@responses.activate
def test_inline_post_failure_404(delivery):
    responses.add(responses.POST, "https://consumer.test/hook", status=404)
    backend = InlineBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is False
    assert result.status_code == 404

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.last_response_status == 404


@responses.activate
def test_inline_post_failure_500(delivery):
    responses.add(responses.POST, "https://consumer.test/hook", status=500, body="Internal Server Error")
    backend = InlineBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is False
    assert result.status_code == 500

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.last_response_body == "Internal Server Error"


# --- Timeout / ConnectionError --------------------------------------------


@responses.activate
def test_inline_post_timeout_marks_failed(delivery):
    responses.add(
        responses.POST, "https://consumer.test/hook",
        body=requests.Timeout("Request timed out"),
    )
    backend = InlineBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is False
    assert result.status_code is None
    assert result.error is not None
    assert "timed out" in result.error.lower() or "timeout" in result.error.lower()

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.last_response_status is None
    assert delivery.last_error != ""


@responses.activate
def test_inline_post_connection_error_marks_failed(delivery):
    responses.add(
        responses.POST, "https://consumer.test/hook",
        body=requests.ConnectionError("DNS failure"),
    )
    backend = InlineBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is False
    assert result.error is not None

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.last_error != ""


# --- attempts counter -----------------------------------------------------


@responses.activate
def test_inline_increments_attempts_counter(delivery):
    """Cada deliver_now increment attempts (manual retry semantics S14.5)."""
    responses.add(responses.POST, "https://consumer.test/hook", status=500)
    backend = InlineBackend()

    backend.deliver_now(delivery.id)
    delivery.refresh_from_db()
    assert delivery.attempts == 1

    backend.deliver_now(delivery.id)
    delivery.refresh_from_db()
    assert delivery.attempts == 2


# --- enqueue (sync delegation) --------------------------------------------


@responses.activate
def test_inline_enqueue_calls_deliver_now(delivery):
    """InlineBackend.enqueue == deliver_now (sync, no async)."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)
    backend = InlineBackend()
    backend.enqueue(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED
    assert delivery.attempts == 1
