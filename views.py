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

"""Inbound webhook view (S14.4 / T3).

Plain Django view (NOT DRF, D3) — receives POST + delegates to
ReceiverDispatcher. csrf_exempt (D4) porque webhooks NO manejan CSRF tokens
(HMAC signature reemplaza CSRF protection).
"""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .receivers.dispatch import ReceiverDispatcher


@method_decorator(csrf_exempt, name="dispatch")
class InboundWebhookView(View):
    """POST /sinpapel/api/webhooks/in/<source>/

    Delegates to ReceiverDispatcher; returns JsonResponse con status code.

    Status codes:
        200: Success (handler invoked) o duplicate (idempotency)
        400: Missing required headers o invalid JSON
        401: HMAC invalid o unknown source
        404: No handler registered for (source, event_type)
        500: Handler raised exception
    """

    def post(self, request: HttpRequest, source: str) -> JsonResponse:
        dispatcher = ReceiverDispatcher()
        body, status_code = dispatcher.dispatch(source, request)
        return JsonResponse(body, status=status_code)
