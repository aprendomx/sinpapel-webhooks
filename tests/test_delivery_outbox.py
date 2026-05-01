"""OutboxBackend tests (S14.2 / T3).

Verifies enqueue no-op + deliver_now retry-aware semantics:
- 2xx → delivered
- 5xx/timeout → pending + scheduled_at_next set (jitter ±10%)
- 4xx semantic → failed (no retry)
- Max attempts → dead_letter
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
import responses
from django.test import override_settings
from django.utils import timezone

from sinpapel_webhooks.delivery.backends.outbox import OutboxBackend
from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.delivery.ports import WebhookDeliveryBackend
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


# --- Fixtures -------------------------------------------------------------


@pytest.fixture
def subscription(db):
    return WebhookSubscription.objects.create(
        name="outbox-sub",
        url="https://consumer.test/hook",
        events=["test.event"],
        secret="outbox-test-secret-32bytes-aaa",
        active=True,
    )


@pytest.fixture
def event(db):
    return WebhookEvent.objects.create(
        event_type="test.event",
        payload={"x": 1},
    )


@pytest.fixture
def delivery(subscription, event):
    return WebhookDelivery.objects.create(subscription=subscription, event=event)


# --- Protocol conformance -------------------------------------------------


def test_outbox_backend_implements_protocol():
    backend = OutboxBackend()
    assert isinstance(backend, WebhookDeliveryBackend)
    assert backend.name == "outbox"


@override_settings(SINPAPEL_WEBHOOKS_BACKEND="outbox")
def test_factory_resolves_outbox_short_name():
    get_delivery_backend.cache_clear()
    backend = get_delivery_backend()
    assert isinstance(backend, OutboxBackend)


# --- enqueue no-op --------------------------------------------------------


def test_outbox_enqueue_is_noop_status_stays_pending(delivery):
    """enqueue NO debe tocar la delivery — worker la procesa."""
    backend = OutboxBackend()
    initial_attempts = delivery.attempts
    initial_status = delivery.status

    backend.enqueue(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == initial_status == WebhookDelivery.STATUS_PENDING
    assert delivery.attempts == initial_attempts == 0
    assert delivery.last_attempt_at is None


# --- deliver_now success path --------------------------------------------


@responses.activate
def test_outbox_deliver_now_success_marks_delivered(delivery):
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    backend = OutboxBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is True
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED
    assert delivery.attempts == 1


# --- 5xx → retry programado -----------------------------------------------


@responses.activate
def test_outbox_deliver_now_5xx_schedules_retry(delivery):
    responses.add(responses.POST, "https://consumer.test/hook", status=500)

    backend = OutboxBackend()
    before = timezone.now()
    backend.deliver_now(delivery.id)

    delivery.refresh_from_db()
    # Status back to pending (retry scheduled)
    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert delivery.attempts == 1
    # scheduled_at moved to future (~60s + jitter)
    delta = (delivery.scheduled_at - before).total_seconds()
    assert 50 < delta < 70  # backoff[0]=60 ± 10%


# --- 4xx semantic → failed sin retry --------------------------------------


@responses.activate
@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_outbox_deliver_now_4xx_semantic_marks_failed_no_retry(delivery, status):
    responses.add(responses.POST, "https://consumer.test/hook", status=status)

    backend = OutboxBackend()
    initial_scheduled_at = delivery.scheduled_at
    backend.deliver_now(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.attempts == 1
    # scheduled_at NO debe avanzar (no retry)
    assert delivery.scheduled_at == initial_scheduled_at


# --- 408/429 transient 4xx → retry ---------------------------------------


@responses.activate
@pytest.mark.parametrize("status", [408, 429])
def test_outbox_deliver_now_transient_4xx_schedules_retry(delivery, status):
    responses.add(responses.POST, "https://consumer.test/hook", status=status)

    backend = OutboxBackend()
    backend.deliver_now(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_PENDING  # retry programado
    assert delivery.attempts == 1


# --- Timeout → retry ------------------------------------------------------


@responses.activate
def test_outbox_deliver_now_timeout_schedules_retry(delivery):
    responses.add(
        responses.POST, "https://consumer.test/hook",
        body=requests.Timeout("Request timed out"),
    )

    backend = OutboxBackend()
    backend.deliver_now(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert delivery.attempts == 1
    assert delivery.last_error != ""


# --- Max attempts → dead_letter -------------------------------------------


@override_settings(SINPAPEL_WEBHOOKS_MAX_ATTEMPTS=3, SINPAPEL_WEBHOOKS_DEAD_LETTER_AFTER_ATTEMPTS=True)
@responses.activate
def test_outbox_deliver_now_max_attempts_marks_dead_letter(delivery):
    responses.add(responses.POST, "https://consumer.test/hook", status=500)

    backend = OutboxBackend()
    # Run 3 attempts (max)
    for _ in range(3):
        backend.deliver_now(delivery.id)

    delivery.refresh_from_db()
    # 3rd attempt → max reached → dead_letter
    assert delivery.status == WebhookDelivery.STATUS_DEAD_LETTER
    assert delivery.attempts == 3


@override_settings(SINPAPEL_WEBHOOKS_MAX_ATTEMPTS=2, SINPAPEL_WEBHOOKS_DEAD_LETTER_AFTER_ATTEMPTS=False)
@responses.activate
def test_outbox_deliver_now_max_attempts_dead_letter_disabled_marks_failed(delivery):
    """Cuando DEAD_LETTER_AFTER_ATTEMPTS=False, max attempts → failed."""
    responses.add(responses.POST, "https://consumer.test/hook", status=500)

    backend = OutboxBackend()
    backend.deliver_now(delivery.id)
    backend.deliver_now(delivery.id)  # max reached

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED
    assert delivery.attempts == 2
