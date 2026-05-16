from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(username="admin-e", password="x", email="a@b.c")  # noqa: S106


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_events_list_returns_delivery_count(api_client, admin_user):
    from sinpapel_webhooks.models import WebhookDelivery, WebhookEvent, WebhookSubscription
    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="x.y", payload={"a": 1})
    WebhookDelivery.objects.create(subscription=sub, event=ev)

    api_client.force_authenticate(admin_user)
    resp = api_client.get("/sinpapel/api/webhooks/admin/events/")
    assert resp.status_code == 200
    results = resp.data["results"] if "results" in resp.data else resp.data
    first = next(r for r in results if r["id"] == ev.pk)
    assert first["delivery_count"] == 1
    assert "deliveries" not in first


@pytest.mark.django_db
def test_events_detail_embeds_deliveries(api_client, admin_user):
    from sinpapel_webhooks.models import WebhookDelivery, WebhookEvent, WebhookSubscription
    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="x.y", payload={"a": 1})
    WebhookDelivery.objects.create(subscription=sub, event=ev)

    api_client.force_authenticate(admin_user)
    resp = api_client.get(f"/sinpapel/api/webhooks/admin/events/{ev.pk}/")
    assert resp.status_code == 200
    assert len(resp.data["deliveries"]) == 1
    assert resp.data["payload"] == {"a": 1}


@pytest.mark.django_db
def test_events_list_filter_by_event_type(api_client, admin_user):
    from sinpapel_webhooks.models import WebhookEvent
    WebhookEvent.objects.create(event_type="foo.bar", payload={})
    WebhookEvent.objects.create(event_type="baz.qux", payload={})

    api_client.force_authenticate(admin_user)
    resp = api_client.get("/sinpapel/api/webhooks/admin/events/?event_type=foo.bar")
    assert resp.status_code == 200
    results = resp.data["results"] if "results" in resp.data else resp.data
    assert all(r["event_type"] == "foo.bar" for r in results)
