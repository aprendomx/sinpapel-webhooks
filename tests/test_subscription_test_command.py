"""Subscription test command tests (S14.6 / T2)."""
from __future__ import annotations

from io import StringIO

import pytest
import responses
from django.core.management import CommandError, call_command

from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


@pytest.fixture
def subscription(db):
    return WebhookSubscription.objects.create(
        name="test-cmd-sub",
        url="https://test-cmd.test/hook",
        events=["webhook.test"],
        secret="cmd-test-secret-32bytes-aaa",
    )


@responses.activate
def test_subscription_test_command_sends_synthetic_payload(subscription):
    """Command envía POST con synthetic payload + cleanup transient event."""
    responses.add(responses.POST, "https://test-cmd.test/hook", status=200)

    initial_event_count = WebhookEvent.objects.count()
    initial_delivery_count = WebhookDelivery.objects.count()

    out = StringIO()
    call_command(
        "sinpapel_webhooks_test_subscription",
        subscription.pk,
        stdout=out,
    )

    output = out.getvalue()
    assert "Test successful" in output or "status=200" in output

    # POST sent
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call.request.url == subscription.url

    # Synthetic event + delivery cleaned up (transient)
    assert WebhookEvent.objects.count() == initial_event_count
    assert WebhookDelivery.objects.count() == initial_delivery_count


def test_subscription_test_command_invalid_id_raises(db):
    with pytest.raises(CommandError, match="not found"):
        call_command("sinpapel_webhooks_test_subscription", 99999, stdout=StringIO())


@responses.activate
def test_subscription_test_command_failed_post_reports_status(subscription):
    """Si consumer URL falla, command reporta status code + cleanup transient."""
    responses.add(responses.POST, "https://test-cmd.test/hook", status=500)

    initial_event_count = WebhookEvent.objects.count()

    out = StringIO()
    call_command("sinpapel_webhooks_test_subscription", subscription.pk, stdout=out)

    output = out.getvalue()
    assert "failed" in output.lower() or "500" in output

    # Synthetic cleanup incluso en fail (try/finally)
    assert WebhookEvent.objects.count() == initial_event_count
