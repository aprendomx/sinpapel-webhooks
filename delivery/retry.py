"""Retry policy (S14.2 / T2, ADR-013).

`should_retry(status_code, error)` — 4xx semantic vs 5xx/timeout differentiation
(D3: hardcoded list 400/401/403/404/410/422 → no retry; 408/429 → retry).

`compute_next_retry_at(attempts, *, backoff_list, jitter_ratio)` — exponential
backoff con jitter ±10% (D2: random.uniform(0.9, 1.1) * base_seconds).
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from django.utils import timezone


# D3: 4xx semantic codes — config error, no retry (Stripe/GitHub pattern)
NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 410, 422})


def should_retry(status_code: int | None, error: str | None) -> bool:
    """True si delivery debe reintentar (5xx/timeout/connection/transient 4xx).

    Args:
        status_code: HTTP response status; None si timeout/connection error.
        error: error message string; None si HTTP response received.

    Returns:
        True para 5xx, timeout, connection error, 408 (timeout), 429 (rate limit).
        False para 2xx (success), 4xx semantic (config error).
    """
    # Transport-level error (no HTTP response) → transient, retry
    if error is not None or status_code is None:
        return True

    # Success → no retry
    if 200 <= status_code < 300:
        return False

    # 4xx semantic (config error) → no retry
    if status_code in NON_RETRYABLE_STATUS_CODES:
        return False

    # Everything else (5xx, 408, 429, redirects, etc.) → retry
    return True


def compute_next_retry_at(
    attempts: int,
    *,
    backoff_list: list[int],
    jitter_ratio: float = 0.1,
) -> datetime:
    """Calcula `scheduled_at` para próximo intento con jitter ±10%.

    Args:
        attempts: número de intento actual (1-indexed; 1 = primer fail).
        backoff_list: list de seconds entre intentos (e.g. [60, 300, 1800, ...]).
        jitter_ratio: ratio ±N para randomization (default 0.1 = ±10%).

    Returns:
        timezone.now() + timedelta(seconds=base_seconds * jitter_factor)

    Notes:
        Si attempts > len(backoff_list), usa el último valor (clamped).
        Jitter ±10% evita thundering herd cuando múltiples deliveries
        fallan al mismo segundo (e.g. consumer URL down).
    """
    if attempts < 1:
        attempts = 1
    # Clamp to last entry if past max
    idx = min(attempts - 1, len(backoff_list) - 1)
    base_seconds = backoff_list[idx]
    jitter_factor = random.uniform(1 - jitter_ratio, 1 + jitter_ratio)
    delta_seconds = base_seconds * jitter_factor
    return timezone.now() + timedelta(seconds=delta_seconds)
