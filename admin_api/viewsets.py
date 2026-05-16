"""DRF ViewSets for the admin REST API."""
from __future__ import annotations

import secrets

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from sinpapel_webhooks.admin_api.permissions import get_admin_permission_class
from sinpapel_webhooks.admin_api.serializers import (
    InboundWebhookEventSerializer,
    WebhookDeliverySerializer,
    WebhookEventDetailSerializer,
    WebhookEventListSerializer,
    WebhookSubscriptionSerializer,
)
from sinpapel_webhooks.delivery.backends.inline import InlineBackend
from sinpapel_webhooks.delivery.factory import get_delivery_backend
from sinpapel_webhooks.models import (
    InboundWebhookEvent,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = WebhookSubscription.objects.all().order_by("-created_at")
    serializer_class = WebhookSubscriptionSerializer
    permission_classes = [get_admin_permission_class()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        out = self.get_serializer(instance, context={"reveal_secret": True, "request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rotate-secret")
    def rotate_secret(self, request, pk=None):
        sub = self.get_object()
        sub.secret = secrets.token_hex(32)
        sub.save(update_fields=["secret", "updated_at"])
        out = self.get_serializer(sub, context={"reveal_secret": True, "request": request})
        return Response(out.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="test")
    def test(self, request, pk=None):
        sub = self.get_object()
        synthetic_event = WebhookEvent.objects.create(
            event_type="webhook.test",
            payload={"test": True, "timestamp": timezone.now().isoformat(), "subscription_id": sub.pk},
        )
        synthetic_delivery = WebhookDelivery.objects.create(subscription=sub, event=synthetic_event)
        try:
            result = InlineBackend().deliver_now(synthetic_delivery.id)
            return Response({
                "success": bool(result.success),
                "status_code": getattr(result, "status_code", None),
                "response_body": (getattr(result, "response_body", "") or "")[:500],
                "error": getattr(result, "error", None),
            })
        finally:
            synthetic_delivery.delete()
            synthetic_event.delete()


class WebhookDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WebhookDelivery.objects.all().order_by("-created_at")
    serializer_class = WebhookDeliverySerializer
    permission_classes = [get_admin_permission_class()]

    def get_queryset(self):
        qs = super().get_queryset()
        status_p = self.request.query_params.get("status")
        sub_p = self.request.query_params.get("subscription")
        since_p = self.request.query_params.get("since")
        if status_p:
            qs = qs.filter(status=status_p)
        if sub_p:
            qs = qs.filter(subscription_id=sub_p)
        if since_p:
            qs = qs.filter(created_at__gte=since_p)
        return qs

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        delivery = self.get_object()
        delivery.status = WebhookDelivery.STATUS_PENDING
        delivery.scheduled_at = timezone.now()
        delivery.save(update_fields=["status", "scheduled_at"])
        get_delivery_backend().enqueue(delivery.pk)
        return Response({"queued": True, "delivery_id": delivery.pk})

    @action(detail=False, methods=["post"], url_path="requeue-dead-letter")
    def requeue_dead_letter(self, request):
        body = request.data or {}
        qs = WebhookDelivery.objects.filter(status=WebhookDelivery.STATUS_DEAD_LETTER)
        if not body.get("all"):
            ids = body.get("ids") or []
            if not ids:
                return Response({"error": "Provide {ids: [...]} or {all: true}"}, status=400)
            qs = qs.filter(pk__in=ids)
        backend = get_delivery_backend()
        ids_requeued: list[int] = []
        for delivery in qs:
            delivery.status = WebhookDelivery.STATUS_PENDING
            delivery.scheduled_at = timezone.now()
            delivery.save(update_fields=["status", "scheduled_at"])
            backend.enqueue(delivery.pk)
            ids_requeued.append(delivery.pk)
        return Response({"requeued": len(ids_requeued), "ids": ids_requeued})


class WebhookEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WebhookEvent.objects.all().order_by("-occurred_at")
    permission_classes = [get_admin_permission_class()]

    def get_serializer_class(self):
        if self.action == "list":
            return WebhookEventListSerializer
        return WebhookEventDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        et = self.request.query_params.get("event_type")
        since = self.request.query_params.get("since")
        if et:
            qs = qs.filter(event_type=et)
        if since:
            qs = qs.filter(occurred_at__gte=since)
        return qs


class InboundWebhookEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InboundWebhookEvent.objects.all().order_by("-received_at")
    serializer_class = InboundWebhookEventSerializer
    permission_classes = [get_admin_permission_class()]

    def get_queryset(self):
        qs = super().get_queryset()
        source = self.request.query_params.get("source")
        hs = self.request.query_params.get("handler_status")
        since = self.request.query_params.get("since")
        if source:
            qs = qs.filter(source=source)
        if hs:
            qs = qs.filter(handler_status=hs)
        if since:
            qs = qs.filter(received_at__gte=since)
        return qs
