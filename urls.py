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
