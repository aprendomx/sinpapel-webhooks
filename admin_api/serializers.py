"""DRF Serializers for admin REST API."""
from __future__ import annotations

from rest_framework import serializers

from sinpapel_webhooks.models import (
    InboundWebhookEvent,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


class _MaskedSecretField(serializers.CharField):
    """CharField that masks `secret` on read unless context['reveal_secret']=True."""

    def to_representation(self, value: str) -> str:
        if self.context.get("reveal_secret"):
            return value
        tail = value[-4:] if value and len(value) >= 4 else value
        return f"***{tail}"


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    secret = _MaskedSecretField(max_length=128, write_only=False)

    class Meta:
        model = WebhookSubscription
        fields = ["id", "name", "url", "events", "secret", "active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance: WebhookSubscription, validated_data: dict) -> WebhookSubscription:
        # Secret is not modifiable via PATCH/PUT — must use rotate-secret endpoint.
        validated_data.pop("secret", None)
        return super().update(instance, validated_data)


class _DeliverySlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ["id", "subscription_id", "status", "attempts", "last_response_status"]


class WebhookDeliverySerializer(serializers.ModelSerializer):
    subscription_name = serializers.CharField(source="subscription.name", read_only=True)
    event_type = serializers.CharField(source="event.event_type", read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            "id", "subscription", "subscription_name", "event", "event_type",
            "status", "attempts", "scheduled_at", "last_attempt_at",
            "last_response_status", "last_response_body", "last_error", "created_at",
        ]
        read_only_fields = fields


class WebhookEventListSerializer(serializers.ModelSerializer):
    delivery_count = serializers.IntegerField(source="deliveries.count", read_only=True)

    class Meta:
        model = WebhookEvent
        fields = ["id", "event_id", "event_type", "occurred_at", "delivery_count"]
        read_only_fields = fields


class WebhookEventDetailSerializer(serializers.ModelSerializer):
    deliveries = _DeliverySlimSerializer(many=True, read_only=True)

    class Meta:
        model = WebhookEvent
        fields = ["id", "event_id", "event_type", "payload", "occurred_at",
                  "source_object_ct", "source_object_id", "deliveries"]
        read_only_fields = fields


class InboundWebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboundWebhookEvent
        fields = ["id", "source", "event_id", "event_type", "received_at", "payload", "handler_status"]
        read_only_fields = fields
