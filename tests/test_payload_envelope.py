"""Payload envelope tests (S14.2 / T3, D4 + D6).

Verifies envelope structure (event_id + event_type + occurred_at + data + metadata)
y subscription_id per-delivery (D6: 2 deliveries de mismo event tienen distinct
subscription_ids in metadata).
"""
from __future__ import annotations

import json

import pytest
import responses

from sinpapel_webhooks.delivery.backends.inline import InlineBackend
from sinpapel_webhooks.delivery.executor import build_envelope
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)
from sinpapel_webhooks.signing import verify_signature


@pytest.fixture
def event(db):
    return WebhookEvent.objects.create(
        event_type="workflow.transition.completed",
        payload={"solicitud_id": 142, "estado_nuevo": "FIRMADO"},
    )


def test_envelope_structure_complete(event):
    """Envelope tiene 5 top-level keys: event_id, event_type, occurred_at, data, metadata."""
    sub = WebhookSubscription.objects.create(
        name="env-sub", url="https://x.test/h",
        events=["workflow.transition.completed"], secret="s",
    )
    delivery = WebhookDelivery.objects.create(subscription=sub, event=event)

    envelope = build_envelope(delivery)

    assert set(envelope.keys()) == {
        "event_id", "event_type", "occurred_at", "data", "metadata",
    }
    assert envelope["event_id"] == str(event.event_id)
    assert envelope["event_type"] == "workflow.transition.completed"
    assert envelope["data"] == event.payload
    assert isinstance(envelope["occurred_at"], str)  # ISO format string


def test_envelope_metadata_includes_versions_and_subscription_id(event):
    sub = WebhookSubscription.objects.create(
        name="meta-sub", url="https://x.test/h",
        events=["t"], secret="s",
    )
    delivery = WebhookDelivery.objects.create(subscription=sub, event=event)

    envelope = build_envelope(delivery)
    metadata = envelope["metadata"]

    assert "sinpapel_version" in metadata
    assert "webhooks_version" in metadata
    assert metadata["subscription_id"] == sub.id
    assert metadata["api_version"] == "2026-04-30"


def test_envelope_subscription_id_varies_per_delivery(event):
    """D6: 2 deliveries de mismo WebhookEvent → metadata.subscription_id distinto."""
    sub_a = WebhookSubscription.objects.create(
        name="a", url="https://a.test/h", events=["t"], secret="s",
    )
    sub_b = WebhookSubscription.objects.create(
        name="b", url="https://b.test/h", events=["t"], secret="s",
    )
    delivery_a = WebhookDelivery.objects.create(subscription=sub_a, event=event)
    delivery_b = WebhookDelivery.objects.create(subscription=sub_b, event=event)

    env_a = build_envelope(delivery_a)
    env_b = build_envelope(delivery_b)

    assert env_a["metadata"]["subscription_id"] == sub_a.id
    assert env_b["metadata"]["subscription_id"] == sub_b.id
    assert env_a["metadata"]["subscription_id"] != env_b["metadata"]["subscription_id"]
    # event_id is shared (same event)
    assert env_a["event_id"] == env_b["event_id"]


@responses.activate
def test_envelope_hmac_round_trip_valid(event):
    """HMAC computed over envelope JSON debe verificar con secret de subscription."""
    sub = WebhookSubscription.objects.create(
        name="hmac-sub", url="https://hmac.test/h",
        events=["workflow.transition.completed"],
        secret="hmac-test-secret-32bytes-aaa",
    )
    delivery = WebhookDelivery.objects.create(subscription=sub, event=event)

    responses.add(responses.POST, "https://hmac.test/h", status=200)

    backend = InlineBackend()
    backend.deliver_now(delivery.id)

    call = responses.calls[0]
    body_bytes = call.request.body
    if isinstance(body_bytes, str):
        body_bytes = body_bytes.encode()

    # HMAC round-trip — body byte-exact (sin re-serialization)
    verify_signature(
        body_bytes,
        call.request.headers["X-Sinpapel-Signature"],
        sub.secret,
        tolerance_seconds=300,
    )

    # Body es JSON parseable y tiene envelope structure
    parsed = json.loads(body_bytes)
    assert "event_id" in parsed
    assert "data" in parsed
    assert parsed["metadata"]["subscription_id"] == sub.id
