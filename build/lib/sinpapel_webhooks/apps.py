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

from django.apps import AppConfig


class SinpapelWebhooksConfig(AppConfig):
    name = "sinpapel_webhooks"
    verbose_name = "Sinpapel Webhooks (event-driven HTTP)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Loose coupling: import signals para registrar @receiver decorators.
        # sinpapel core NO importa nada de sinpapel_webhooks; webhooks listens
        # via signal.connect a sinpapel models declarados con sender="sinpapel.X".
        from . import signals  # noqa: F401

        # S14.4: auto-discover consumer apps con webhooks.py module.
        # Django convention — same pattern como admin.autodiscover().
        # Apps sin webhooks.py silently skipped.
        from django.utils.module_loading import autodiscover_modules
        autodiscover_modules("webhooks")
