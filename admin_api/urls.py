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
