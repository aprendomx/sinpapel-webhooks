"""sinpapel-webhooks models — persistencia para outbound + inbound.

4 modelos:
- WebhookSubscription: configuración consumer de URLs + events + secret (outbound).
- WebhookEvent: canonical event log emitido por sinpapel domain events.
- WebhookDelivery: delivery attempt log por (subscription, event).
- InboundWebhookEvent: idempotency dedup table para inbound (S14.4).
"""
from __future__ import annotations

import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


class WebhookSubscription(models.Model):
    """Outbound subscription — consumer registra URL para recibir eventos."""

    name = models.CharField(max_length=200)
    url = models.URLField(max_length=2000)
    events = models.JSONField(
        default=list,
        help_text="Lista de event_type a los que la subscription reacciona (ej. ['workflow.transition.completed']).",
    )
    secret = models.CharField(
        max_length=128,
        help_text="Secret HMAC per-subscription (32-byte hex típico). Visible solo al crear.",
    )
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Webhook Subscription"
        verbose_name_plural = "Webhook Subscriptions"
        indexes = [
            models.Index(fields=["active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} → {self.url}"


class WebhookEvent(models.Model):
    """Canonical event log — emitido por sinpapel core domain events.

    GFK opcional al objeto fuente (Solicitud, RegistroFirma, InstanciaDocumento)
    para linkback en admin (S14.5) sin acoplar event al tipo del source.
    """

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    occurred_at = models.DateTimeField(default=timezone.now)
    source_object_ct = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    source_object_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Webhook Event"
        verbose_name_plural = "Webhook Events"
        indexes = [
            models.Index(fields=["event_type", "-occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.occurred_at:%Y-%m-%d %H:%M:%S} ({self.event_id})"


class WebhookDelivery(models.Model):
    """Delivery attempt log — uno por (subscription, event)."""

    STATUS_PENDING = "pending"
    STATUS_DELIVERING = "delivering"
    STATUS_DELIVERED = "delivered"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_DELIVERING, "Delivering"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_FAILED, "Failed"),
    ]

    subscription = models.ForeignKey(
        WebhookSubscription, on_delete=models.CASCADE, related_name="deliveries",
    )
    event = models.ForeignKey(
        WebhookEvent, on_delete=models.CASCADE, related_name="deliveries",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    scheduled_at = models.DateTimeField(default=timezone.now)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_response_status = models.IntegerField(null=True, blank=True)
    last_response_body = models.TextField(blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Webhook Delivery"
        verbose_name_plural = "Webhook Deliveries"
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),  # outbox worker query
            models.Index(fields=["subscription", "-created_at"]),  # admin filter
        ]

    def __str__(self) -> str:
        return f"Delivery #{self.pk} sub={self.subscription_id} event={self.event_id} [{self.status}]"


class InboundWebhookEvent(models.Model):
    """Idempotency dedup table para inbound webhooks (S14.4).

    Unique on (source, event_id) — duplicate POST → 200 OK sin re-invocar handler.
    """

    HANDLER_PROCESSED = "processed"
    HANDLER_ERROR = "error"
    HANDLER_DUPLICATE = "duplicate"
    HANDLER_NO_HANDLER = "no_handler"

    HANDLER_STATUS_CHOICES = [
        (HANDLER_PROCESSED, "Processed"),
        (HANDLER_ERROR, "Error"),
        (HANDLER_DUPLICATE, "Duplicate"),
        (HANDLER_NO_HANDLER, "No Handler"),
    ]

    source = models.CharField(max_length=100)
    event_id = models.CharField(max_length=200)  # external event ID (UUID/ULID/string)
    event_type = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()
    handler_status = models.CharField(
        max_length=20, choices=HANDLER_STATUS_CHOICES, default=HANDLER_PROCESSED,
    )

    class Meta:
        verbose_name = "Inbound Webhook Event"
        verbose_name_plural = "Inbound Webhook Events"
        unique_together = [("source", "event_id")]
        indexes = [
            models.Index(fields=["source", "-received_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source}/{self.event_type}#{self.event_id} [{self.handler_status}]"
