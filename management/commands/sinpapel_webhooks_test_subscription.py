"""sinpapel_webhooks_test_subscription — operator command (S14.6 / T2).

Send synthetic test payload a la URL de una subscription para validar
URL+secret antes de activar consumer real. Force inline backend para
sync feedback. Synthetic event es transient (cleanup post-send; D5).

Usage:
    manage.py sinpapel_webhooks_test_subscription <subscription_id>
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from sinpapel_webhooks.delivery.backends.inline import InlineBackend
from sinpapel_webhooks.models import (
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


class Command(BaseCommand):
    help = "Send synthetic test payload a la URL de una subscription (NO persist event)."

    def add_arguments(self, parser):
        parser.add_argument(
            "subscription_id",
            type=int,
            help="ID de WebhookSubscription a testear",
        )

    def handle(self, *args, **options):
        sub_id = options["subscription_id"]
        try:
            sub = WebhookSubscription.objects.get(pk=sub_id)
        except WebhookSubscription.DoesNotExist as e:
            raise CommandError(f"WebhookSubscription id={sub_id} not found") from e

        # Synthetic event — transient (deleted en finally)
        synthetic_event = WebhookEvent.objects.create(
            event_type="webhook.test",
            payload={
                "test": True,
                "timestamp": timezone.now().isoformat(),
                "subscription_id": sub.pk,
            },
        )
        synthetic_delivery = WebhookDelivery.objects.create(
            subscription=sub,
            event=synthetic_event,
        )

        try:
            self.stdout.write(
                f"Sending synthetic test payload to {sub.url}..."
            )
            result = InlineBackend().deliver_now(synthetic_delivery.id)
            if result.success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Test successful: status={result.status_code}, "
                        f"body={(result.response_body or '')[:200]}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"✗ Test failed: status={result.status_code}, "
                        f"error={result.error}, "
                        f"body={(result.response_body or '')[:200]}"
                    )
                )
        finally:
            # Cleanup synthetic — NO pollute persistent data
            synthetic_delivery.delete()
            synthetic_event.delete()
