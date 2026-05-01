"""sinpapel-webhooks URL routing (S14.4 / T3, D1).

Inbound webhook endpoint. Consumer wires up via:

    # mossc/urls.py
    urlpatterns = [
        path("sinpapel/api/webhooks/", include("sinpapel_webhooks.urls")),
    ]

D1 architectural deviation (epic design.md §3.6): URL routing en
sinpapel_webhooks PROPIO (NOT en sinpapel_drf) para preservar loose coupling.
Plain Django view sufficient para server-to-server JSON.
"""
from __future__ import annotations

from django.urls import path

from .views import InboundWebhookView


app_name = "sinpapel_webhooks"

urlpatterns = [
    path("in/<str:source>/", InboundWebhookView.as_view(), name="inbound"),
]
