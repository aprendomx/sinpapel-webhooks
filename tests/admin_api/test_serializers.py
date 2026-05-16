from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_subscription_serializer_masks_secret_on_read():
    from sinpapel_webhooks.admin_api.serializers import WebhookSubscriptionSerializer
    from sinpapel_webhooks.models import WebhookSubscription

    sub = WebhookSubscription.objects.create(
        name="s", url="https://x.test/h", events=["a"], secret="abcd1234efgh5678", active=True,
    )
    data = WebhookSubscriptionSerializer(sub).data
    assert data["secret"] == "***5678"
    assert "id" in data
    assert data["events"] == ["a"]


@pytest.mark.django_db
def test_subscription_serializer_creates_with_secret_visible_in_response():
    from sinpapel_webhooks.admin_api.serializers import WebhookSubscriptionSerializer

    ser = WebhookSubscriptionSerializer(data={
        "name": "new", "url": "https://x.test/h", "events": ["a"],
        "secret": "fullsecretvalue12345",
    })
    assert ser.is_valid(), ser.errors
    sub = ser.save()
    # to_representation runs after create; reveal secret on the create response.
    out = WebhookSubscriptionSerializer(sub, context={"reveal_secret": True}).data
    assert out["secret"] == "fullsecretvalue12345"


@pytest.mark.django_db
def test_event_serializer_list_returns_delivery_count_only():
    from sinpapel_webhooks.admin_api.serializers import WebhookEventListSerializer
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription, WebhookDelivery

    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="t", payload={"a": 1})
    WebhookDelivery.objects.create(subscription=sub, event=ev)
    WebhookDelivery.objects.create(subscription=sub, event=ev)

    data = WebhookEventListSerializer(ev).data
    assert data["delivery_count"] == 2
    assert "deliveries" not in data


@pytest.mark.django_db
def test_event_serializer_detail_embeds_deliveries():
    from sinpapel_webhooks.admin_api.serializers import WebhookEventDetailSerializer
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription, WebhookDelivery

    sub = WebhookSubscription.objects.create(name="s", url="https://x.test/h", events=[], secret="s")
    ev = WebhookEvent.objects.create(event_type="t", payload={"a": 1})
    WebhookDelivery.objects.create(subscription=sub, event=ev)

    data = WebhookEventDetailSerializer(ev).data
    assert len(data["deliveries"]) == 1
    d = data["deliveries"][0]
    assert d["status"] == "pending"
    assert d["subscription_id"] == sub.pk
