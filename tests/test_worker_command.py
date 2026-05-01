"""Worker management command tests (S14.2 / T4).

Verifies --once / --batch-size / --poll-interval semantics +
SKIP LOCKED query (PG only) + KeyboardInterrupt graceful shutdown.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
import responses
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


@pytest.fixture(autouse=True)
def _outbox_backend():
    """Worker requiere outbox backend."""
    get_delivery_backend.cache_clear()
    with override_settings(SINPAPEL_WEBHOOKS_BACKEND="outbox"):
        yield
    get_delivery_backend.cache_clear()


def _make_delivery(*, scheduled_at=None) -> WebhookDelivery:
    sub = WebhookSubscription.objects.create(
        name=f"worker-sub-{WebhookSubscription.objects.count()}",
        url="https://consumer.test/hook",
        events=["t"], secret="s", active=True,
    )
    event = WebhookEvent.objects.create(event_type="t", payload={})
    kwargs = {"subscription": sub, "event": event}
    if scheduled_at is not None:
        kwargs["scheduled_at"] = scheduled_at
    return WebhookDelivery.objects.create(**kwargs)


# --- --once mode ---------------------------------------------------------


@responses.activate
def test_worker_once_drains_pending_and_exits(db):
    """--once procesa pending y termina (no infinite loop)."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    deliveries = [_make_delivery() for _ in range(3)]

    out = StringIO()
    call_command("sinpapel_webhooks_worker", once=True, stdout=out)

    output = out.getvalue()
    assert "drained 3 deliveries" in output.lower()

    for d in deliveries:
        d.refresh_from_db()
        assert d.status == WebhookDelivery.STATUS_DELIVERED


# --- --batch-size limit --------------------------------------------------


@responses.activate
def test_worker_batch_size_limits_processing(db):
    """--batch-size N procesa max N deliveries per poll."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    [_make_delivery() for _ in range(5)]

    out = StringIO()
    call_command("sinpapel_webhooks_worker", once=True, batch_size=3, stdout=out)

    delivered = WebhookDelivery.objects.filter(status=WebhookDelivery.STATUS_DELIVERED).count()
    pending = WebhookDelivery.objects.filter(status=WebhookDelivery.STATUS_PENDING).count()
    assert delivered == 3
    assert pending == 2


# --- scheduled_at__gt=now skipped ----------------------------------------


@responses.activate
def test_worker_skips_pending_with_future_scheduled_at(db):
    """Pending con scheduled_at en futuro NO se procesa."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)

    future = timezone.now() + timedelta(hours=1)
    future_delivery = _make_delivery(scheduled_at=future)
    now_delivery = _make_delivery()  # scheduled_at = default now

    call_command("sinpapel_webhooks_worker", once=True, stdout=StringIO())

    future_delivery.refresh_from_db()
    now_delivery.refresh_from_db()
    assert future_delivery.status == WebhookDelivery.STATUS_PENDING  # NO procesado
    assert now_delivery.status == WebhookDelivery.STATUS_DELIVERED


# --- KeyboardInterrupt graceful shutdown ----------------------------------


@responses.activate
def test_worker_keyboard_interrupt_graceful_shutdown(db):
    """SIGINT/Ctrl+C → 'Graceful shutdown' message + exit clean."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)
    _make_delivery()

    # Mock time.sleep para raise KeyboardInterrupt en el poll wait
    out = StringIO()
    with patch(
        "sinpapel_webhooks.management.commands.sinpapel_webhooks_worker.time.sleep",
        side_effect=KeyboardInterrupt,
    ):
        # No --once, so worker enters poll loop after first drain
        call_command("sinpapel_webhooks_worker", batch_size=10, poll_interval=1, stdout=out)

    output = out.getvalue()
    assert "graceful shutdown" in output.lower()


# --- PostgreSQL SKIP LOCKED query verification ---------------------------


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="SKIP LOCKED is PostgreSQL-specific (PG 9.5+)",
)
@responses.activate
def test_worker_pg_uses_skip_locked_query(db):
    """D5: PostgreSQL workers usan SELECT FOR UPDATE SKIP LOCKED."""
    responses.add(responses.POST, "https://consumer.test/hook", status=200)
    _make_delivery()

    queries_captured = []

    original_execute = connection.cursor().__class__.execute

    def capture_execute(self, sql, params=None):
        queries_captured.append(str(sql))
        return original_execute(self, sql, params)

    with patch.object(connection.cursor().__class__, "execute", capture_execute):
        call_command("sinpapel_webhooks_worker", once=True, stdout=StringIO())

    skip_locked_used = any(
        "SKIP LOCKED" in q.upper() or "FOR UPDATE" in q.upper()
        for q in queries_captured
    )
    assert skip_locked_used, "Expected SELECT FOR UPDATE SKIP LOCKED in queries"
