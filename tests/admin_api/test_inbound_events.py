from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(username="admin-i", password="x", email="a@b.c")  # noqa: S106


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_inbound_events_list_filters_by_source(api_client, admin_user):
    from sinpapel_webhooks.models import InboundWebhookEvent
    InboundWebhookEvent.objects.create(source="bar", event_id="e1", event_type="t", payload={})
    InboundWebhookEvent.objects.create(source="baz", event_id="e2", event_type="t", payload={})

    api_client.force_authenticate(admin_user)
    resp = api_client.get("/sinpapel/api/webhooks/admin/inbound-events/?source=bar")
    assert resp.status_code == 200
    results = resp.data["results"] if "results" in resp.data else resp.data
    assert all(r["source"] == "bar" for r in results)
