"""URL routing for the admin REST API."""
from __future__ import annotations

from rest_framework.routers import DefaultRouter

from sinpapel_webhooks.admin_api.viewsets import (
    InboundWebhookEventViewSet,
    WebhookDeliveryViewSet,
    WebhookEventViewSet,
    WebhookSubscriptionViewSet,
)

router = DefaultRouter()
router.register(r"subscriptions", WebhookSubscriptionViewSet, basename="subscription")
router.register(r"deliveries", WebhookDeliveryViewSet, basename="delivery")
router.register(r"events", WebhookEventViewSet, basename="event")
router.register(r"inbound-events", InboundWebhookEventViewSet, basename="inboundevent")

urlpatterns = router.urls
