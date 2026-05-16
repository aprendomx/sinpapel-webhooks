from __future__ import annotations

import pytest


def test_get_admin_permission_class_returns_default_is_admin_user(settings):
    from sinpapel_webhooks.admin_api.permissions import get_admin_permission_class
    from rest_framework.permissions import IsAdminUser

    if hasattr(settings, "SINPAPEL_WEBHOOKS_ADMIN_PERMISSION"):
        del settings.SINPAPEL_WEBHOOKS_ADMIN_PERMISSION

    cls = get_admin_permission_class()
    assert cls is IsAdminUser


def test_get_admin_permission_class_resolves_dotted_path(settings):
    settings.SINPAPEL_WEBHOOKS_ADMIN_PERMISSION = "rest_framework.permissions.IsAuthenticated"
    from sinpapel_webhooks.admin_api.permissions import get_admin_permission_class
    from rest_framework.permissions import IsAuthenticated

    cls = get_admin_permission_class()
    assert cls is IsAuthenticated


def test_get_admin_permission_class_raises_on_bad_path(settings):
    settings.SINPAPEL_WEBHOOKS_ADMIN_PERMISSION = "nonexistent.module.Class"
    from django.core.exceptions import ImproperlyConfigured
    from sinpapel_webhooks.admin_api.permissions import get_admin_permission_class

    with pytest.raises(ImproperlyConfigured):
        get_admin_permission_class()
