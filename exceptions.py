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
