"""Models tests (S14.1 / T2).

CRUD + indexes + unique_together + history audit para los 4 modelos:
WebhookSubscription, WebhookEvent, WebhookDelivery, InboundWebhookEvent.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from sinpapel_webhooks.models import (
    InboundWebhookEvent,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


# --- WebhookSubscription --------------------------------------------------


@pytest.mark.django_db
def test_webhook_subscription_create_minimal():
    sub = WebhookSubscription.objects.create(
        name="test-sub",
        url="https://example.test/hook",
        events=["workflow.transition.completed"],
        secret="test-secret-32bytes",
    )
    assert sub.pk is not None
    assert sub.active is True  # default
    assert sub.events == ["workflow.transition.completed"]
    assert sub.created_at is not None
    assert sub.updated_at is not None


@pytest.mark.django_db
def test_webhook_subscription_with_user():
    user = User.objects.create_user(username="admin", password="x")  # noqa: S106
    sub = WebhookSubscription.objects.create(
        name="user-sub",
        url="https://example.test/hook",
        events=["a"],
        secret="s",
        created_by=user,
    )
    assert sub.created_by_id == user.id


@pytest.mark.django_db
def test_webhook_subscription_history_audit():
    """HistoricalRecords debe trackear cambios."""
    sub = WebhookSubscription.objects.create(
        name="audit-sub", url="https://x.test/h", events=["e"], secret="s",
    )
    sub.active = False
    sub.save()
    assert sub.history.count() == 2  # create + update


@pytest.mark.django_db
def test_webhook_subscription_active_index_present():
    indexes = [list(idx.fields) for idx in WebhookSubscription._meta.indexes]
    assert ["active"] in indexes


# --- WebhookEvent ---------------------------------------------------------


@pytest.mark.django_db
def test_webhook_event_create_with_uuid_default():
    event = WebhookEvent.objects.create(
        event_type="workflow.transition.completed",
        payload={"solicitud_id": 1},
    )
    assert isinstance(event.event_id, uuid.UUID)
    assert event.occurred_at is not None


@pytest.mark.django_db
def test_webhook_event_event_id_unique():
    fixed_uuid = uuid.uuid4()
    WebhookEvent.objects.create(event_id=fixed_uuid, event_type="t", payload={})
    with pytest.raises(IntegrityError):
        WebhookEvent.objects.create(event_id=fixed_uuid, event_type="t2", payload={})


@pytest.mark.django_db
def test_webhook_event_indexes_present():
    indexes = [list(idx.fields) for idx in WebhookEvent._meta.indexes]
    assert ["event_type", "-occurred_at"] in indexes


# --- WebhookDelivery ------------------------------------------------------


@pytest.mark.django_db
def test_webhook_delivery_create():
    sub = WebhookSubscription.objects.create(
        name="ds", url="https://x.test/h", events=["e"], secret="s",
    )
    event = WebhookEvent.objects.create(event_type="e", payload={})
    delivery = WebhookDelivery.objects.create(subscription=sub, event=event)
    assert delivery.status == "pending"  # default
    assert delivery.attempts == 0
    assert delivery.scheduled_at is not None


@pytest.mark.django_db
def test_webhook_delivery_status_choices():
    """Status debe limitarse a las 4 choices iniciales (S14.1)."""
    valid_statuses = {"pending", "delivering", "delivered", "failed"}
    field = WebhookDelivery._meta.get_field("status")
    actual = {choice[0] for choice in field.choices}
    assert valid_statuses.issubset(actual)


@pytest.mark.django_db
def test_webhook_delivery_indexes_present():
    indexes = [list(idx.fields) for idx in WebhookDelivery._meta.indexes]
    assert ["status", "scheduled_at"] in indexes
    assert ["subscription", "-created_at"] in indexes


@pytest.mark.django_db
def test_webhook_delivery_cascade_on_subscription_delete():
    sub = WebhookSubscription.objects.create(
        name="x", url="https://x.test/h", events=["e"], secret="s",
    )
    event = WebhookEvent.objects.create(event_type="e", payload={})
    WebhookDelivery.objects.create(subscription=sub, event=event)

    sub.delete()
    assert WebhookDelivery.objects.count() == 0


# --- InboundWebhookEvent --------------------------------------------------


@pytest.mark.django_db
def test_inbound_webhook_event_create():
    event = InboundWebhookEvent.objects.create(
        source="baz",
        event_id="ext-event-001",
        event_type="payment.confirmed",
        payload={"amount": 100},
    )
    assert event.received_at is not None
    assert event.handler_status == "processed"  # default


@pytest.mark.django_db
def test_inbound_webhook_event_unique_together():
    """(source, event_id) debe ser unique — idempotency dedup."""
    InboundWebhookEvent.objects.create(
        source="baz", event_id="dup-001", event_type="x", payload={},
    )
    with pytest.raises(IntegrityError):
        InboundWebhookEvent.objects.create(
            source="baz", event_id="dup-001", event_type="y", payload={},
        )


@pytest.mark.django_db
def test_inbound_webhook_event_different_source_same_event_id_ok():
    """Same event_id en distintas fuentes es válido."""
    InboundWebhookEvent.objects.create(
        source="baz", event_id="evt-001", event_type="x", payload={},
    )
    # Distinta source → OK
    InboundWebhookEvent.objects.create(
        source="moneygram", event_id="evt-001", event_type="x", payload={},
    )
    assert InboundWebhookEvent.objects.count() == 2


@pytest.mark.django_db
def test_inbound_webhook_event_indexes_present():
    indexes = [list(idx.fields) for idx in InboundWebhookEvent._meta.indexes]
    assert ["source", "-received_at"] in indexes
