"""Dispatcher tests (S14.4 / T2).

Verifies 9-step dispatch flow via 11 scenarios covering all status codes:
200 success / 200 duplicate / 400 missing-headers / 400 invalid-JSON /
401 invalid-HMAC / 401 unknown-source / 404 no-handler / 500 handler-exception.
"""
from __future__ import annotations

import json
import time

import pytest
from django.test import RequestFactory, override_settings

from sinpapel_webhooks.models import InboundWebhookEvent
from sinpapel_webhooks.receivers.dispatch import ReceiverDispatcher
from sinpapel_webhooks.receivers.registry import (
    InboundReceiverRegistry,
    webhook_receiver,
)
from sinpapel_webhooks.signing import compute_signature


SECRET = "test-secret-32bytes-aaa-bbb-ccc"


@pytest.fixture(autouse=True)
def _clear_registry():
    InboundReceiverRegistry.clear()
    yield
    InboundReceiverRegistry.clear()


@pytest.fixture
def rf():
    return RequestFactory()


def _make_signed_request(rf, source, event_id, event_type, body_dict, secret):
    """Construye HttpRequest signed con HMAC válido."""
    body = json.dumps(body_dict).encode()
    ts = int(time.time())
    signature = compute_signature(body, secret, timestamp=ts)
    request = rf.post(
        f"/sinpapel/api/webhooks/in/{source}/",
        data=body,
        content_type="application/json",
        headers={
            "X-Sinpapel-Signature": signature,
            "X-Sinpapel-Event-Id": event_id,
            "X-Sinpapel-Event-Type": event_type,
        },
    )
    return request


# --- 200 success path -----------------------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_valid_hmac_invokes_handler(rf):
    @webhook_receiver(source="test_source", event="ping")
    def handler(payload, request):
        return {"acked": True, "received": payload}

    request = _make_signed_request(rf, "test_source", "evt-001", "ping", {"hello": "x"}, SECRET)
    body, status = ReceiverDispatcher().dispatch("test_source", request)

    assert status == 200
    assert body == {"acked": True, "received": {"hello": "x"}}

    # InboundWebhookEvent persisted con handler_status="processed"
    event = InboundWebhookEvent.objects.get(source="test_source", event_id="evt-001")
    assert event.handler_status == InboundWebhookEvent.HANDLER_PROCESSED


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_handler_returns_none_defaults_to_acked(rf):
    @webhook_receiver(source="test_source", event="silent")
    def handler(payload, request):
        return None  # Handler returns None

    request = _make_signed_request(rf, "test_source", "evt-002", "silent", {}, SECRET)
    body, status = ReceiverDispatcher().dispatch("test_source", request)

    assert status == 200
    assert body == {"acked": True}


# --- 401 HMAC / source errors --------------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_invalid_hmac_returns_401(rf):
    request = _make_signed_request(rf, "test_source", "evt-bad", "ping", {}, "wrong-secret")
    body, status = ReceiverDispatcher().dispatch("test_source", request)

    assert status == 401
    assert "error" in body
    # NO event persisted (HMAC fails before idempotency check)
    assert InboundWebhookEvent.objects.count() == 0


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={})
def test_dispatch_unknown_source_returns_401(rf):
    request = _make_signed_request(rf, "unknown_source", "evt", "ping", {}, SECRET)
    body, status = ReceiverDispatcher().dispatch("unknown_source", request)

    assert status == 401
    assert "Unknown source" in body["error"]


# --- 400 missing headers / invalid JSON ----------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_missing_event_id_returns_400(rf):
    body_dict = {"x": 1}
    body = json.dumps(body_dict).encode()
    ts = int(time.time())
    signature = compute_signature(body, SECRET, timestamp=ts)
    request = rf.post(
        "/sinpapel/api/webhooks/in/test_source/",
        data=body, content_type="application/json",
        headers={
            "X-Sinpapel-Signature": signature,
            # Missing X-Sinpapel-Event-Id
            "X-Sinpapel-Event-Type": "ping",
        },
    )
    response_body, status = ReceiverDispatcher().dispatch("test_source", request)
    assert status == 400
    assert "Missing" in response_body["error"]


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_invalid_json_body_returns_400(rf):
    body = b"not valid json {{{"
    ts = int(time.time())
    signature = compute_signature(body, SECRET, timestamp=ts)
    request = rf.post(
        "/sinpapel/api/webhooks/in/test_source/",
        data=body, content_type="application/json",
        headers={
            "X-Sinpapel-Signature": signature,
            "X-Sinpapel-Event-Id": "evt-bad-json",
            "X-Sinpapel-Event-Type": "ping",
        },
    )
    response_body, status = ReceiverDispatcher().dispatch("test_source", request)
    assert status == 400
    assert "Invalid JSON" in response_body["error"]


# --- 200 duplicate (idempotency) -----------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_duplicate_event_id_returns_200_no_reinvoke(rf):
    invocations = []

    @webhook_receiver(source="test_source", event="ping")
    def handler(payload, request):
        invocations.append(payload)
        return {"acked": True}

    # First request — handler invoked
    request1 = _make_signed_request(rf, "test_source", "dup-001", "ping", {"n": 1}, SECRET)
    _, status1 = ReceiverDispatcher().dispatch("test_source", request1)
    assert status1 == 200
    assert len(invocations) == 1

    # Second request, mismo event_id — duplicate detected
    request2 = _make_signed_request(rf, "test_source", "dup-001", "ping", {"n": 2}, SECRET)
    body2, status2 = ReceiverDispatcher().dispatch("test_source", request2)
    assert status2 == 200
    assert body2 == {"acked": True, "duplicate": True}
    # Handler NOT re-invoked
    assert len(invocations) == 1
    # Solo 1 InboundWebhookEvent (unique_together protege)
    assert InboundWebhookEvent.objects.filter(event_id="dup-001").count() == 1


# --- 404 no handler -------------------------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_no_handler_returns_404(rf):
    request = _make_signed_request(rf, "test_source", "evt-nohandler", "unregistered.event", {}, SECRET)
    body, status = ReceiverDispatcher().dispatch("test_source", request)

    assert status == 404
    assert "No handler" in body["error"]

    event = InboundWebhookEvent.objects.get(event_id="evt-nohandler")
    assert event.handler_status == InboundWebhookEvent.HANDLER_NO_HANDLER


# --- 500 handler exception -----------------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_source": SECRET})
def test_dispatch_handler_exception_returns_500(rf):
    @webhook_receiver(source="test_source", event="boom")
    def handler(payload, request):
        raise ValueError("intentional test failure")

    request = _make_signed_request(rf, "test_source", "evt-boom", "boom", {}, SECRET)
    body, status = ReceiverDispatcher().dispatch("test_source", request)

    assert status == 500
    assert "Handler raised" in body["error"]
    assert "ValueError" in body["error"]

    event = InboundWebhookEvent.objects.get(event_id="evt-boom")
    assert event.handler_status == InboundWebhookEvent.HANDLER_ERROR
