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

"""sinpapel-webhooks — event-driven HTTP communication para sinpapel.

Outbound: signal hooks escuchando eventos del dominio sinpapel
(workflow transitions, signatures, document changes) → POSTs HMAC-firmados
a URLs configuradas vía WebhookSubscription. Pluggable delivery backends
(inline / outbox / celery, ADR-013).

Inbound: receiver framework con @webhook_receiver decorator + HMAC verification
+ idempotency dedup. Routing en sinpapel_webhooks/urls.py propio (S14.4 D1).

Public API:
    from sinpapel_webhooks import webhook_receiver, __version__
"""
__version__ = "0.2.4"

# Lazy re-export to avoid Django app loading issues at module import time
def __getattr__(name: str):
    if name == "webhook_receiver":
        from .receivers.registry import webhook_receiver
        return webhook_receiver
    raise AttributeError(f"module 'sinpapel_webhooks' has no attribute {name!r}")


__all__ = ["__version__", "webhook_receiver"]
