"""HMAC-SHA256 signing tests (S14.1 / T1) — ADR-014.

Incluye 5 known-good test vectors hardcoded como regression protection
contra refactor accidental que rompa el algoritmo silenciosamente.

Algorithm: HMAC-SHA256 sobre `f"{ts}.".encode() + payload`.
Header format: `t=<unix-ts>,v1=<hex>` (Stripe-compatible).
"""
from __future__ import annotations

import hmac
import time

import pytest

from sinpapel_webhooks.exceptions import WebhookSignatureError
from sinpapel_webhooks.signing import compute_signature, verify_signature


# Known-good vectors: (payload, secret, timestamp, expected_signature_hex)
# Computados al implementar S14.1/T1; cualquier change → CI fails.
KNOWN_VECTORS: list[tuple[bytes, str, int, str]] = [
    (
        b'{"event":"test"}',
        "secret-1",
        1714492800,
        "05c4246fd4034c697643eb53689e27872fe159e55f61b78b9bd7d16e1c354632",
    ),
    (
        b"",
        "empty-payload",
        1714492800,
        "fc7a1d9be128dedfbe265fb47f1446e537f4538cafa7ebf31474b9cc5fcada13",
    ),
    (
        b'{"a":1,"b":2}',
        "abc",
        1714492800,
        "1bc8adc077dc0dc4e2ac016acc3c42df9025ba08e39578bc43c14f3b4d0f541a",
    ),
    (
        b'{"unicode":"\xc3\xa9"}',  # é encoded UTF-8
        "utf8",
        1714492800,
        "d32f20cf8bf978643122e0be7ccfcc550eaee3d391aa76de3af195ab06f854a0",
    ),
    (
        b"x" * 1024,
        "long-payload-secret",
        1714492800,
        "84398e7cbae72aeb8c0ab15c70f98d5f46b6954d1fcdc2d7c832f0403ddbf029",
    ),
]


# --- compute_signature ----------------------------------------------------


@pytest.mark.parametrize("payload,secret,ts,expected_hex", KNOWN_VECTORS)
def test_compute_signature_known_vectors(payload, secret, ts, expected_hex):
    """5 known-good vectors regression protection."""
    result = compute_signature(payload, secret, timestamp=ts)
    assert result == f"t={ts},v1={expected_hex}"


def test_compute_signature_uses_now_when_no_timestamp():
    """Sin timestamp explícito, usa int(time.time())."""
    before = int(time.time())
    sig = compute_signature(b"x", "s")
    after = int(time.time())

    parts = dict(p.split("=", 1) for p in sig.split(","))
    ts = int(parts["t"])
    assert before <= ts <= after
    assert "v1" in parts
    assert len(parts["v1"]) == 64  # sha256 hex


def test_compute_signature_deterministic():
    """Mismos inputs → mismo output."""
    a = compute_signature(b'{"x":1}', "secret", timestamp=1700000000)
    b = compute_signature(b'{"x":1}', "secret", timestamp=1700000000)
    assert a == b


def test_compute_signature_different_payload_different_signature():
    a = compute_signature(b'{"x":1}', "secret", timestamp=1700000000)
    b = compute_signature(b'{"x":2}', "secret", timestamp=1700000000)
    assert a != b


def test_compute_signature_different_secret_different_signature():
    a = compute_signature(b"payload", "secret-a", timestamp=1700000000)
    b = compute_signature(b"payload", "secret-b", timestamp=1700000000)
    assert a != b


# --- verify_signature -----------------------------------------------------


def test_verify_signature_valid_round_trip():
    """compute → verify roundtrip funciona."""
    payload = b'{"event":"x"}'
    secret = "round-trip-secret"
    ts = int(time.time())
    header = compute_signature(payload, secret, timestamp=ts)

    # No raise
    verify_signature(payload, header, secret, tolerance_seconds=300)


def test_verify_signature_rejects_tampered_payload():
    secret = "s"
    ts = int(time.time())
    header = compute_signature(b'{"a":1}', secret, timestamp=ts)

    with pytest.raises(WebhookSignatureError, match="Signature mismatch"):
        verify_signature(b'{"a":2}', header, secret, tolerance_seconds=300)


def test_verify_signature_rejects_wrong_secret():
    secret = "real-secret"
    ts = int(time.time())
    header = compute_signature(b"payload", secret, timestamp=ts)

    with pytest.raises(WebhookSignatureError, match="Signature mismatch"):
        verify_signature(b"payload", header, "wrong-secret", tolerance_seconds=300)


def test_verify_signature_rejects_old_timestamp():
    """Replay protection: timestamp >tolerance segundos viejo → reject."""
    secret = "s"
    old_ts = int(time.time()) - 600  # 10 min en el pasado
    header = compute_signature(b"payload", secret, timestamp=old_ts)

    with pytest.raises(WebhookSignatureError, match="Timestamp outside tolerance"):
        verify_signature(b"payload", header, secret, tolerance_seconds=300)


def test_verify_signature_rejects_future_timestamp():
    """Replay protection: timestamp >tolerance segundos en futuro → reject."""
    secret = "s"
    future_ts = int(time.time()) + 600
    header = compute_signature(b"payload", secret, timestamp=future_ts)

    with pytest.raises(WebhookSignatureError, match="Timestamp outside tolerance"):
        verify_signature(b"payload", header, secret, tolerance_seconds=300)


def test_verify_signature_accepts_timestamp_within_tolerance():
    """Tolerance: timestamp dentro de window → pasa."""
    secret = "s"
    ts = int(time.time()) - 250  # 250s en el pasado, dentro de tolerance=300
    header = compute_signature(b"payload", secret, timestamp=ts)

    verify_signature(b"payload", header, secret, tolerance_seconds=300)


@pytest.mark.parametrize("malformed_header", [
    "no-equals-here",
    "t=1714492800",  # falta v1
    "v1=abc",  # falta t
    "t=not-an-int,v1=abc",
    "",
    "t=1,v1=abc,extra",  # OK estructura pero parses con junk en valores; Y verifica como malformado
])
def test_verify_signature_rejects_malformed_header(malformed_header):
    with pytest.raises(WebhookSignatureError):
        verify_signature(b"payload", malformed_header, "secret", tolerance_seconds=300)


def test_verify_signature_uses_constant_time_compare():
    """Constant-time compare resistance verificada vía hmac.compare_digest usage.

    No podemos testar timing directamente sin flaky tests; verificamos que el
    módulo importa hmac.compare_digest (introspection ligera).
    """
    import sinpapel_webhooks.signing as sm
    src = open(sm.__file__).read()
    assert "hmac.compare_digest" in src, "verify_signature debe usar hmac.compare_digest"
