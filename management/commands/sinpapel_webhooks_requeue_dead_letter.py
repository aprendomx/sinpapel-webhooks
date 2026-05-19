# sinpapel-webhooks — event-driven HTTP communication for sinpapel.
# Copyright (C) 2024-2026 Julio Adrián <jadrian.s@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""sinpapel_webhooks_requeue_dead_letter — operator command (S14.6 / T2).

Re-queue WebhookDelivery rows en status='dead_letter' a status='pending' con
scheduled_at=now y attempts=0 (fresh retry chain).

Usage:
    # Re-queue ALL dead_letter deliveries
    manage.py sinpapel_webhooks_requeue_dead_letter --all

    # Re-queue specific delivery
    manage.py sinpapel_webhooks_requeue_dead_letter --id 142

Args mutually exclusive (D4); requires explicit choice (avoid accidental requeue).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from sinpapel_webhooks.models import WebhookDelivery


class Command(BaseCommand):
    help = "Re-queue WebhookDelivery rows en status='dead_letter' a 'pending'."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--all",
            action="store_true",
            help="Re-queue todas las deliveries en status='dead_letter'.",
        )
        group.add_argument(
            "--id",
            type=int,
            metavar="N",
            help="Re-queue specific delivery por ID.",
        )

    def handle(self, *args, **options):
        all_flag = options["all"]
        delivery_id = options["id"]

        qs = WebhookDelivery.objects.filter(
            status=WebhookDelivery.STATUS_DEAD_LETTER,
        )
        if not all_flag:
            qs = qs.filter(pk=delivery_id)

        count = qs.update(
            status=WebhookDelivery.STATUS_PENDING,
            scheduled_at=timezone.now(),
            attempts=0,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Re-queued {count} dead_letter deliveries")
        )
