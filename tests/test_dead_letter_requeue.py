"""Dead letter requeue command tests (S14.6 / T2)."""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


@pytest.fixture
def dead_letter_delivery(db):
    sub = WebhookSubscription.objects.create(
        name="dl-sub", url="https://x.test/h", events=["t"], secret="s",
    )
    event = WebhookEvent.objects.create(event_type="t", payload={})
    return WebhookDelivery.objects.create(
        subscription=sub, event=event,
        status=WebhookDelivery.STATUS_DEAD_LETTER,
        attempts=5,
    )


def test_requeue_all_resets_status_and_attempts(db):
    """--all re-queue todas las dead_letter; status="pending", attempts=0."""
    sub = WebhookSubscription.objects.create(
        name="x", url="https://x.test/h", events=["t"], secret="s",
    )
    event = WebhookEvent.objects.create(event_type="t", payload={})
    for _ in range(3):
        WebhookDelivery.objects.create(
            subscription=sub, event=event,
            status=WebhookDelivery.STATUS_DEAD_LETTER, attempts=5,
        )
    # 1 delivery con status delivered (NO debe ser tocado)
    WebhookDelivery.objects.create(
        subscription=sub, event=event,
        status=WebhookDelivery.STATUS_DELIVERED, attempts=1,
    )

    out = StringIO()
    call_command("sinpapel_webhooks_requeue_dead_letter", all=True, stdout=out)

    assert "Re-queued 3" in out.getvalue()
    # 3 dead_letter → pending
    assert WebhookDelivery.objects.filter(status=WebhookDelivery.STATUS_PENDING).count() == 3
    # delivered no tocado
    assert WebhookDelivery.objects.filter(status=WebhookDelivery.STATUS_DELIVERED).count() == 1
    # attempts reset
    for d in WebhookDelivery.objects.filter(status=WebhookDelivery.STATUS_PENDING):
        assert d.attempts == 0


def test_requeue_specific_id(dead_letter_delivery):
    """--id N re-queue solo la specific delivery."""
    out = StringIO()
    call_command(
        "sinpapel_webhooks_requeue_dead_letter",
        id=dead_letter_delivery.pk,
        stdout=out,
    )

    assert "Re-queued 1" in out.getvalue()
    dead_letter_delivery.refresh_from_db()
    assert dead_letter_delivery.status == WebhookDelivery.STATUS_PENDING
    assert dead_letter_delivery.attempts == 0


def test_requeue_no_args_raises(db):
    """Sin --all ni --id → error (mutually exclusive group required)."""
    with pytest.raises((CommandError, SystemExit)):
        call_command("sinpapel_webhooks_requeue_dead_letter", stdout=StringIO())


def test_requeue_id_not_dead_letter_no_op(db):
    """--id N de delivery NOT en dead_letter → 0 re-queued."""
    sub = WebhookSubscription.objects.create(
        name="x", url="https://x.test/h", events=["t"], secret="s",
    )
    event = WebhookEvent.objects.create(event_type="t", payload={})
    delivery = WebhookDelivery.objects.create(
        subscription=sub, event=event,
        status=WebhookDelivery.STATUS_DELIVERED, attempts=1,
    )

    out = StringIO()
    call_command("sinpapel_webhooks_requeue_dead_letter", id=delivery.pk, stdout=out)

    assert "Re-queued 0" in out.getvalue()
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED  # unchanged
