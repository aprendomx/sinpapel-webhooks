"""HMAC-SHA256 signing per ADR-014.

Header format Stripe-compatible: `X-Sinpapel-Signature: t=<unix-ts>,v1=<sha256-hex>`.

Algorithm:
    signed_payload = f"{timestamp}.".encode() + payload_bytes
    signature = HMAC-SHA256(secret, signed_payload).hexdigest()
    header = f"t={timestamp},v1={signature}"

Replay protection: timestamp tolerance window (default 300s).
Tampering protection: HMAC + constant-time compare via hmac.compare_digest.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from .exceptions import WebhookSignatureError


def compute_signature(payload: bytes, secret: str, *, timestamp: int | None = None) -> str:
    """Genera el valor del header X-Sinpapel-Signature.

    Args:
        payload: raw bytes del body request (NO json re-serialization;
                 el HMAC depende de los bytes exactos enviados).
        secret: subscription/source secret (32-byte hex típico).
        timestamp: unix seconds; default = int(time.time()).

    Returns:
        "t=<unix-ts>,v1=<sha256-hex>"
    """
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def verify_signature(
    payload: bytes,
    header_value: str,
    secret: str,
    *,
    tolerance_seconds: int = 300,
) -> None:
    """Valida HMAC + timestamp tolerance window.

    Args:
        payload: raw bytes del body request recibido.
        header_value: valor exacto del header X-Sinpapel-Signature.
        secret: secret esperado para verificar.
        tolerance_seconds: ventana ± segundos para timestamp (replay protection).

    Raises:
        WebhookSignatureError: si header malformado, timestamp drift > tolerance,
                               o signature mismatch.
    """
    # Parse header
    try:
        parts = dict(p.split("=", 1) for p in header_value.split(","))
    except ValueError as e:
        raise WebhookSignatureError(f"Malformed signature header: {e}") from e

    if "t" not in parts or "v1" not in parts:
        raise WebhookSignatureError(
            "Malformed signature header: missing 't' or 'v1' component"
        )

    try:
        ts = int(parts["t"])
    except ValueError as e:
        raise WebhookSignatureError(f"Malformed signature header: invalid timestamp: {e}") from e

    received_sig = parts["v1"]

    # Replay protection
    drift = abs(time.time() - ts)
    if drift > tolerance_seconds:
        raise WebhookSignatureError(
            f"Timestamp outside tolerance window ({drift:.0f}s > {tolerance_seconds}s)"
        )

    # Compute expected + constant-time compare
    expected_sig = hmac.new(
        secret.encode(),
        f"{ts}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, received_sig):
        raise WebhookSignatureError("Signature mismatch")
