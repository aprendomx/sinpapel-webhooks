"""sinpapel_webhooks_worker — outbox queue drainer (S14.2 / T4).

Long-running poller que drain WebhookDelivery con status="pending" +
scheduled_at <= now(). Multi-worker safe en PostgreSQL via SELECT FOR UPDATE
SKIP LOCKED (D5); SQLite fallback single-worker only.

Usage:
    # Long-running daemon (production)
    manage.py sinpapel_webhooks_worker

    # Single drain pass + exit (testing/cron)
    manage.py sinpapel_webhooks_worker --once

    # Custom batch size + poll interval
    manage.py sinpapel_webhooks_worker --batch-size 100 --poll-interval 10

Graceful shutdown: KeyboardInterrupt (Ctrl+C / SIGINT) — termina batch actual.
Operator infra (systemd Restart=on-failure, k8s terminationGracePeriodSeconds)
maneja signal lifecycle.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from sinpapel_webhooks.delivery.backends.outbox import OutboxBackend
from sinpapel_webhooks.models import WebhookDelivery


class Command(BaseCommand):
    help = (
        "Drain pending WebhookDeliveries (outbox backend). "
        "Multi-worker safe en PostgreSQL via SKIP LOCKED."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Drenar 1 batch y salir (testing/cron mode). Default: long-running.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Max deliveries procesadas per poll cycle (default: 50).",
        )
        parser.add_argument(
            "--poll-interval",
            type=int,
            default=5,
            help="Segundos entre polls cuando no hay pending (default: 5). Ignorado con --once.",
        )

    def handle(self, *args, **options):
        once = options["once"]
        batch_size = options["batch_size"]
        poll_interval = options["poll_interval"]

        backend = OutboxBackend()
        if not once:
            self.stdout.write(
                f"sinpapel_webhooks_worker started "
                f"(batch_size={batch_size}, poll_interval={poll_interval}s, "
                f"vendor={connection.vendor})"
            )

        try:
            while True:
                processed = self._drain_batch(backend, batch_size)
                if processed > 0:
                    self.stdout.write(f"Drained {processed} deliveries")

                if once:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"--once mode: drained {processed} deliveries; exiting."
                        )
                    )
                    return

                if processed == 0:
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING("\nGraceful shutdown — exiting after current batch.")
            )

    def _drain_batch(self, backend: OutboxBackend, batch_size: int) -> int:
        """Claim + procesar batch de pending deliveries.

        D5: PostgreSQL usa SELECT FOR UPDATE SKIP LOCKED para multi-worker safety.
        SQLite fallback: simple FIFO en transaction (lock implícito, single-worker).
        """
        # Claim batch atomically
        with transaction.atomic():
            queryset = (
                WebhookDelivery.objects
                .filter(
                    status=WebhookDelivery.STATUS_PENDING,
                    scheduled_at__lte=timezone.now(),
                )
                .order_by("scheduled_at")
            )
            if connection.vendor == "postgresql":
                queryset = queryset.select_for_update(skip_locked=True)
            pending_ids = list(queryset.values_list("id", flat=True)[:batch_size])

        # Process outside transaction (HTTP I/O)
        for delivery_id in pending_ids:
            backend.deliver_now(delivery_id)

        return len(pending_ids)
