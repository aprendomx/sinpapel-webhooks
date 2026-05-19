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

"""Permission resolver — reads SINPAPEL_WEBHOOKS_ADMIN_PERMISSION setting."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

DEFAULT_PERMISSION_DOTTED = "rest_framework.permissions.IsAdminUser"


def get_admin_permission_class() -> Any:
    """Resolve the configured permission class.

    Reads `SINPAPEL_WEBHOOKS_ADMIN_PERMISSION` (dotted path); defaults to
    `rest_framework.permissions.IsAdminUser`.

    Raises:
        ImproperlyConfigured: if the dotted path cannot be imported.
    """
    dotted = getattr(settings, "SINPAPEL_WEBHOOKS_ADMIN_PERMISSION", DEFAULT_PERMISSION_DOTTED)
    try:
        return import_string(dotted)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"SINPAPEL_WEBHOOKS_ADMIN_PERMISSION={dotted!r} could not be imported: {exc}"
        ) from exc
