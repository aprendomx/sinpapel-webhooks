from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(username="admin", password="x", email="a@b.c")  # noqa: S106


@pytest.fixture
def non_admin(db):
    return User.objects.create_user(username="bob", password="x")  # noqa: S106


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_subscription_list_requires_admin(api_client, non_admin):
    api_client.force_authenticate(non_admin)
    resp = api_client.get("/sinpapel/api/webhooks/admin/subscriptions/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_subscription_create_returns_secret_once(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    resp = api_client.post(
        "/sinpapel/api/webhooks/admin/subscriptions/",
        data={
            "name": "ops",
            "url": "https://ops.test/hook",
            "events": ["workflow.transition.completed"],
            "secret": "supersecret-32-bytes-fully-revealed",
            "active": True,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["secret"] == "supersecret-32-bytes-fully-revealed"


@pytest.mark.django_db
def test_subscription_retrieve_masks_secret(api_client, admin_user):
    from sinpapel_webhooks.models import WebhookSubscription
    sub = WebhookSubscription.objects.create(
        name="s", url="https://x.test/h", events=["a"], secret="abcd1234efgh5678", active=True,
    )
    api_client.force_authenticate(admin_user)
    resp = api_client.get(f"/sinpapel/api/webhooks/admin/subscriptions/{sub.pk}/")
    assert resp.status_code == 200
    assert resp.data["secret"] == "***5678"


@pytest.mark.django_db
def test_subscription_rotate_secret_returns_new_secret_once(api_client, admin_user):
    from sinpapel_webhooks.models import WebhookSubscription
    sub = WebhookSubscription.objects.create(
        name="s", url="https://x.test/h", events=["a"], secret="oldsecret-xxxx", active=True,
    )
    api_client.force_authenticate(admin_user)
    resp = api_client.post(f"/sinpapel/api/webhooks/admin/subscriptions/{sub.pk}/rotate-secret/")
    assert resp.status_code == 200
    new_secret = resp.data["secret"]
    assert new_secret != "oldsecret-xxxx"
    assert len(new_secret) >= 32
    sub.refresh_from_db()
    assert sub.secret == new_secret


@pytest.mark.django_db
def test_subscription_test_action_invokes_inline_backend(api_client, admin_user, monkeypatch):
    from sinpapel_webhooks.models import WebhookSubscription
    sub = WebhookSubscription.objects.create(
        name="s", url="https://x.test/h", events=["a"], secret="s", active=True,
    )
    api_client.force_authenticate(admin_user)

    called = {"count": 0}

    class _FakeResult:
        success = True
        status_code = 200
        response_body = "OK"
        error = None

    def fake_deliver_now(self, delivery_id):
        called["count"] += 1
        return _FakeResult()

    monkeypatch.setattr(
        "sinpapel_webhooks.delivery.backends.inline.InlineBackend.deliver_now",
        fake_deliver_now,
    )
    resp = api_client.post(f"/sinpapel/api/webhooks/admin/subscriptions/{sub.pk}/test/")
    assert resp.status_code == 200
    assert resp.data["success"] is True
    assert called["count"] == 1
