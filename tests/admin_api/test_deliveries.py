from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(username="admin-d", password="x", email="a@b.c")  # noqa: S106


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_deliveries_list_filters_by_status(api_client, admin_user):
    from sinpapel_webhooks.models import WebhookDelivery, WebhookEvent, WebhookSubscription
    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="t", payload={})
    WebhookDelivery.objects.create(subscription=sub, event=ev, status=WebhookDelivery.STATUS_PENDING)
    WebhookDelivery.objects.create(subscription=sub, event=ev, status=WebhookDelivery.STATUS_DELIVERED)

    api_client.force_authenticate(admin_user)
    resp = api_client.get("/sinpapel/api/webhooks/admin/deliveries/?status=delivered")
    assert resp.status_code == 200
    results = resp.data["results"] if "results" in resp.data else resp.data
    assert all(r["status"] == "delivered" for r in results)


@pytest.mark.django_db
def test_delivery_retry_resets_status_and_enqueues(api_client, admin_user, monkeypatch):
    from sinpapel_webhooks.models import WebhookDelivery, WebhookEvent, WebhookSubscription
    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="t", payload={})
    delivery = WebhookDelivery.objects.create(
        subscription=sub, event=ev, status=WebhookDelivery.STATUS_FAILED,
    )

    calls: list[int] = []
    monkeypatch.setattr(
        "sinpapel_webhooks.admin_api.viewsets.get_delivery_backend",
        lambda: type("B", (), {"enqueue": lambda self, did: calls.append(did)})(),
    )

    api_client.force_authenticate(admin_user)
    resp = api_client.post(f"/sinpapel/api/webhooks/admin/deliveries/{delivery.pk}/retry/")
    assert resp.status_code == 200
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert calls == [delivery.pk]


@pytest.mark.django_db
def test_requeue_dead_letter_all(api_client, admin_user, monkeypatch):
    from sinpapel_webhooks.models import WebhookDelivery, WebhookEvent, WebhookSubscription
    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="t", payload={})
    d1 = WebhookDelivery.objects.create(subscription=sub, event=ev, status=WebhookDelivery.STATUS_DEAD_LETTER)
    d2 = WebhookDelivery.objects.create(subscription=sub, event=ev, status=WebhookDelivery.STATUS_DEAD_LETTER)

    calls: list[int] = []
    monkeypatch.setattr(
        "sinpapel_webhooks.admin_api.viewsets.get_delivery_backend",
        lambda: type("B", (), {"enqueue": lambda self, did: calls.append(did)})(),
    )
    api_client.force_authenticate(admin_user)
    resp = api_client.post(
        "/sinpapel/api/webhooks/admin/deliveries/requeue-dead-letter/",
        data={"all": True}, format="json",
    )
    assert resp.status_code == 200
    assert resp.data["requeued"] == 2
    assert set(calls) == {d1.pk, d2.pk}
