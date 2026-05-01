"""emit_event tests (S14.1 / T4).

Verifies subscription filter (active + events__contains), delivery creation,
backend.enqueue invocation, GFK populating.

S14.2 update: default backend cambió a "outbox" (enqueue no-op). Tests aquí
override a "inline" para validar emit_event semantics inmediatas (deliver
sync vs persistir pending).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
import responses
from django.test import override_settings

from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.emit import emit_event
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


@pytest.fixture(autouse=True)
def _use_inline_backend():
    """S14.2: default backend cambió a outbox; estos tests asumen inline."""
    get_delivery_backend.cache_clear()
    with override_settings(SINPAPEL_WEBHOOKS_BACKEND="inline"):
        yield
    get_delivery_backend.cache_clear()


@pytest.fixture
def mock_url():
    return "https://consumer.test/hook"


@pytest.fixture
def mock_post(mock_url):
    """Mock all POST to mock_url returning 200 (so InlineBackend doesn't fail)."""
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, mock_url, status=200)
        yield rsps


# --- Persistence ----------------------------------------------------------


@pytest.mark.django_db
def test_emit_event_creates_webhook_event():
    event = emit_event("test.event", {"key": "value"})
    assert isinstance(event, WebhookEvent)
    assert event.event_type == "test.event"
    assert event.payload == {"key": "value"}
    assert WebhookEvent.objects.count() == 1


@pytest.mark.django_db
def test_emit_event_no_subscriptions_no_deliveries():
    """Sin subscriptions activas → 0 deliveries."""
    event = emit_event("test.event", {})
    assert event.deliveries.count() == 0
    assert WebhookDelivery.objects.count() == 0


# --- Subscription filter (D1) --------------------------------------------


@pytest.mark.django_db
def test_emit_event_creates_delivery_for_matching_subscription(db, mock_url, mock_post):
    sub = WebhookSubscription.objects.create(
        name="match", url=mock_url,
        events=["test.event"], secret="s", active=True,
    )
    event = emit_event("test.event", {"x": 1})
    assert event.deliveries.count() == 1
    delivery = event.deliveries.first()
    assert delivery.subscription_id == sub.id


@pytest.mark.django_db
def test_emit_event_skips_inactive_subscription(db, mock_url):
    WebhookSubscription.objects.create(
        name="inactive", url=mock_url,
        events=["test.event"], secret="s", active=False,
    )
    event = emit_event("test.event", {})
    assert event.deliveries.count() == 0


@pytest.mark.django_db
def test_emit_event_skips_non_matching_event(db, mock_url):
    WebhookSubscription.objects.create(
        name="other", url=mock_url,
        events=["different.event"], secret="s", active=True,
    )
    event = emit_event("test.event", {})
    assert event.deliveries.count() == 0


@pytest.mark.django_db
def test_emit_event_creates_one_delivery_per_matching_sub(db, mock_url, mock_post):
    """Múltiples subs activas matching → múltiples deliveries (1 por sub)."""
    for n in range(3):
        WebhookSubscription.objects.create(
            name=f"sub-{n}", url=mock_url,
            events=["test.event"], secret="s", active=True,
        )
    event = emit_event("test.event", {})
    assert event.deliveries.count() == 3


@pytest.mark.django_db
def test_emit_event_handles_subscription_with_multiple_events(db, mock_url, mock_post):
    """Subscription con múltiples events → matchea uno cualquiera."""
    sub = WebhookSubscription.objects.create(
        name="multi", url=mock_url,
        events=["a.event", "b.event", "c.event"], secret="s", active=True,
    )
    event_a = emit_event("a.event", {})
    event_c = emit_event("c.event", {})
    assert event_a.deliveries.count() == 1
    assert event_c.deliveries.count() == 1
    # 2 deliveries totales (una por emit)
    assert WebhookDelivery.objects.filter(subscription=sub).count() == 2


# --- backend.enqueue invocation ------------------------------------------


@pytest.mark.django_db
def test_emit_event_invokes_backend_enqueue(db, mock_url):
    """emit_event llama backend.enqueue() por cada delivery creado."""
    WebhookSubscription.objects.create(
        name="x", url=mock_url, events=["test"], secret="s", active=True,
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend") as mock_factory:
        mock_backend = mock_factory.return_value
        emit_event("test", {})
        assert mock_backend.enqueue.called
        assert mock_backend.enqueue.call_count == 1


@pytest.mark.django_db
def test_emit_event_no_backend_call_when_no_subscriptions(db):
    """Sin subscriptions matching → backend NO se invoca."""
    with patch("sinpapel_webhooks.emit.get_delivery_backend") as mock_factory:
        emit_event("test", {})
        # Factory might be called pero enqueue no
        if mock_factory.called:
            assert not mock_factory.return_value.enqueue.called


# --- GFK populating (D3) -------------------------------------------------


@pytest.mark.django_db
def test_emit_event_populates_gfk_when_source_provided(db):
    """source kwarg → source_object_ct + source_object_id persisted."""
    sub = WebhookSubscription.objects.create(
        name="x", url="https://x.test/h", events=["t"], secret="s",
    )
    event = emit_event("evt", {}, source=sub)  # cualquier Model funciona aquí

    assert event.source_object_id == sub.pk
    assert event.source_object_ct is not None
    assert event.source_object_ct.model == "webhooksubscription"


@pytest.mark.django_db
def test_emit_event_no_gfk_when_no_source(db):
    """Sin source → GFK fields = None."""
    event = emit_event("evt", {})
    assert event.source_object_id is None
    assert event.source_object_ct is None
