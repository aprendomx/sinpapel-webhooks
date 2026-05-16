"""Root URLConf used by the test suite.

Mounts sinpapel-webhooks under the same prefix used by consumer projects
(`sinpapel/api/webhooks/`) so URL routing tests with hard-coded paths work.
"""
from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("sinpapel/api/webhooks/", include("sinpapel_webhooks.urls")),
]
