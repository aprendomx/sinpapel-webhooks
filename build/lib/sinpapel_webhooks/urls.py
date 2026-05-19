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

"""sinpapel-webhooks URL routing.

Mounts:
- POST /in/<source>/        Inbound receiver (always available).
- /admin/                   Admin REST API (only if DRF is installed).

Consumer wires up via:
    path("sinpapel/api/webhooks/", include("sinpapel_webhooks.urls"))
"""
from __future__ import annotations

from django.urls import include, path

from .views import InboundWebhookView

app_name = "sinpapel_webhooks"

urlpatterns = [
    path("in/<str:source>/", InboundWebhookView.as_view(), name="inbound"),
]

# Admin REST API — gated by DRF being importable AND the `[admin]` extra installed.
try:
    import rest_framework  # noqa: F401
    from .admin_api.urls import urlpatterns as _admin_urls  # noqa: F401
except ImportError:
    pass
else:
    urlpatterns += [path("admin/", include((_admin_urls, "admin_api"), namespace="admin"))]
