"""CeleryBackend tests (S14.3 / T1).

Tests usan `CELERY_TASK_ALWAYS_EAGER=True` para sync execution sin broker.
Verifica Protocol conformance + factory + enqueue dispatch + executor reuse +
retry policy via eager mode.
"""
from __future__ import annotations

import pytest
import responses
from django.test import override_settings

from sinpapel_webhooks.delivery.backends.celery import (
    CeleryBackend,
    _deliver_webhook_task,
)
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
        name="celery-sub",
        url="https://consumer.test/hook",
        events=["test.event"],
        secret="celery-test-secret-32bytes-aaa",
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


@pytest.fixture(autouse=True)
def _eager_celery():
    """Sync execution sin broker para todos los tests.

    Celery NO lee settings via Django override_settings — usa su propio config
    object. Configurar `current_app.conf.task_always_eager` directamente.
    """
    from celery import current_app
    original_eager = current_app.conf.task_always_eager
    original_propagates = current_app.conf.task_eager_propagates
    current_app.conf.task_always_eager = True
    current_app.conf.task_eager_propagates = True
    yield
    current_app.conf.task_always_eager = original_eager
    current_app.conf.task_eager_propagates = original_propagates


# --- Protocol conformance + factory --------------------------------------


def test_celery_backend_implements_protocol():
    backend = CeleryBackend()
    assert isinstance(backend, WebhookDeliveryBackend)
    assert backend.name == "celery"


@override_settings(SINPAPEL_WEBHOOKS_BACKEND="celery")
def test_celery_factory_resolves_short_name():
    get_delivery_backend.cache_clear()
    backend = get_delivery_backend()
    assert isinstance(backend, CeleryBackend)


# --- enqueue dispatcha task -----------------------------------------------


@responses.activate
def test_celery_enqueue_dispatches_task(delivery):
    """En eager mode, .delay() ejecuta sync via executor → POST."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    backend = CeleryBackend()
    backend.enqueue(delivery.id)

    # En eager mode el task ejecutó sync; POST sucedió
    assert len(responses.calls) == 1
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED


# --- Eager mode success path ----------------------------------------------


@responses.activate
def test_celery_eager_mode_marks_delivered_on_success(delivery):
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    backend = CeleryBackend()
    backend.enqueue(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED
    assert delivery.attempts == 1
    assert delivery.last_response_status == 200


# --- Retry policy via shared executor -------------------------------------


@responses.activate
def test_celery_eager_mode_5xx_schedules_retry(delivery):
    """Verifica retry policy aplicada via shared executor con allow_retry=True."""
    responses.add(responses.POST, "https://consumer.test/hook", status=500)

    backend = CeleryBackend()
    backend.enqueue(delivery.id)

    delivery.refresh_from_db()
    # 5xx → retry programado (NOT failed inmediato — same as outbox)
    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert delivery.attempts == 1


@responses.activate
@pytest.mark.parametrize("status", [400, 404, 422])
def test_celery_eager_mode_4xx_semantic_marks_failed(delivery, status):
    """4xx semantic → failed sin retry (mismo behavior que outbox)."""
    responses.add(responses.POST, "https://consumer.test/hook", status=status)

    backend = CeleryBackend()
    backend.enqueue(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_FAILED


# --- deliver_now manual retry path ----------------------------------------


@responses.activate
def test_celery_deliver_now_via_executor_manual_retry_path(delivery):
    """deliver_now ejecuta sync via executor con allow_retry=True."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    backend = CeleryBackend()
    result = backend.deliver_now(delivery.id)

    assert result.success is True
    assert result.status_code == 200
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DELIVERED


# --- Task return shape ----------------------------------------------------


@responses.activate
def test_deliver_webhook_task_returns_serializable_dict(delivery):
    """Task return value debe ser JSON-serializable (Celery requirement)."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    result = _deliver_webhook_task(delivery.id)
    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["delivery_id"] == delivery.id
