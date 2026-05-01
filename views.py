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
