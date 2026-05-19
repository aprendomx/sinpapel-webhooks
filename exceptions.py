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

"""sinpapel-webhooks exceptions."""
from __future__ import annotations


class SinpapelWebhooksError(Exception):
    """Base class para excepciones de sinpapel-webhooks."""


class WebhookSignatureError(SinpapelWebhooksError):
    """Raised cuando la HMAC signature no valida.

    Causas posibles:
    - Header X-Sinpapel-Signature malformado (no parseable como t=<ts>,v1=<hex>).
    - Timestamp fuera de tolerance window (replay protection).
    - Signature mismatch (secret incorrecto o payload alterado).
    """


class WebhookDeliveryError(SinpapelWebhooksError):
    """Raised por delivery backends en errores no recuperables.

    Errores transient (timeout, connection error, 5xx) NO levantan esta
    excepción — quedan persistidos en WebhookDelivery.last_error y disparan
    retry según política del backend.
    """


class WebhookReceiverNotFound(SinpapelWebhooksError):
    """Raised por dispatcher inbound (S14.4) cuando no hay handler registrado
    para (source, event_type)."""
