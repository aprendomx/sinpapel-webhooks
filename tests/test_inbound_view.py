"""Inbound view tests (S14.4 / T3).

Verifies URL routing + csrf_exempt + Django test client integration end-to-end.
Validates D1 (URL en sinpapel_webhooks) + D3 (plain Django view) + D4 (csrf_exempt).
"""
from __future__ import annotations

import json
import time

import pytest
from django.test import Client, override_settings
from django.urls import resolve, reverse

from sinpapel_webhooks.receivers.registry import (
    InboundReceiverRegistry,
    webhook_receiver,
)
from sinpapel_webhooks.signing import compute_signature
from sinpapel_webhooks.views import InboundWebhookView


SECRET = "view-test-secret-32bytes-aaa-bbb"


@pytest.fixture(autouse=True)
def _clear_registry():
    InboundReceiverRegistry.clear()
    yield
    InboundReceiverRegistry.clear()


# --- URL routing ---------------------------------------------------------


def test_post_url_routing_resolves_to_view():
    """URL `/sinpapel/api/webhooks/in/<source>/` resuelve a InboundWebhookView."""
    match = resolve("/sinpapel/api/webhooks/in/baz/")
    assert match.func.view_class is InboundWebhookView
    assert match.kwargs == {"source": "baz"}


def test_url_reverse_works():
    """Reverse URL lookup via app_name + name."""
    url = reverse("sinpapel_webhooks:inbound", kwargs={"source": "baz"})
    assert url == "/sinpapel/api/webhooks/in/baz/"


# --- E2E via Django test client ------------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"baz": SECRET})
def test_post_valid_request_returns_200():
    """E2E: full URL routing + view + dispatcher + handler."""
    @webhook_receiver(source="baz", event="payment.confirmed")
    def handler(payload, request):
        return {"acked": True, "pago_id": payload["pago_id"]}

    body_dict = {"pago_id": 142}
    body = json.dumps(body_dict).encode()
    ts = int(time.time())
    signature = compute_signature(body, SECRET, timestamp=ts)

    client = Client()
    response = client.post(
        "/sinpapel/api/webhooks/in/baz/",
        data=body,
        content_type="application/json",
        headers={
            "X-Sinpapel-Signature": signature,
            "X-Sinpapel-Event-Id": "evt-view-001",
            "X-Sinpapel-Event-Type": "payment.confirmed",
        },
    )

    assert response.status_code == 200
    body_response = response.json()
    assert body_response["acked"] is True
    assert body_response["pago_id"] == 142


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"baz": SECRET})
def test_post_invalid_hmac_returns_401():
    body = json.dumps({"x": 1}).encode()
    ts = int(time.time())
    # Sign con wrong secret
    bad_signature = compute_signature(body, "wrong-secret", timestamp=ts)

    client = Client()
    response = client.post(
        "/sinpapel/api/webhooks/in/baz/",
        data=body,
        content_type="application/json",
        headers={
            "X-Sinpapel-Signature": bad_signature,
            "X-Sinpapel-Event-Id": "evt-bad",
            "X-Sinpapel-Event-Type": "payment.confirmed",
        },
    )

    assert response.status_code == 401
    assert "error" in response.json()


# --- csrf_exempt verified ------------------------------------------------


@pytest.mark.django_db
@override_settings(SINPAPEL_WEBHOOKS_INBOUND_SECRETS={"test_csrf": SECRET})
def test_csrf_exempt_no_token_required():
    """D4: csrf_exempt — POST sin CSRF cookie/token funciona."""
    @webhook_receiver(source="test_csrf", event="ping")
    def handler(payload, request):
        return None

    body = json.dumps({}).encode()
    ts = int(time.time())
    signature = compute_signature(body, SECRET, timestamp=ts)

    # Client SIN CSRF token; enforce_csrf_checks=True para validar D4
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/sinpapel/api/webhooks/in/test_csrf/",
        data=body,
        content_type="application/json",
        headers={
            "X-Sinpapel-Signature": signature,
            "X-Sinpapel-Event-Id": "evt-csrf",
            "X-Sinpapel-Event-Type": "ping",
        },
    )

    # Si csrf_exempt NO aplicado, response sería 403 (CSRF check failed)
    assert response.status_code == 200, (
        f"csrf_exempt may not be applied — got status {response.status_code}"
    )
