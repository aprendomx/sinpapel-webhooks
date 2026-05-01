"""Retry policy tests (S14.2 / T2).

Verifies should_retry() 4xx vs 5xx differentiation + compute_next_retry_at()
backoff progression with jitter.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from sinpapel_webhooks.delivery.retry import (
    NON_RETRYABLE_STATUS_CODES,
    compute_next_retry_at,
    should_retry,
)


# --- should_retry: 4xx semantic vs 5xx differentiation -------------------


@pytest.mark.parametrize("status", [500, 502, 503, 504, 521, 599])
def test_should_retry_5xx_returns_true(status):
    assert should_retry(status, error=None) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_should_retry_4xx_semantic_returns_false(status):
    """D3: hardcoded list — config error, no retry."""
    assert should_retry(status, error=None) is False


@pytest.mark.parametrize("status", [408, 429])
def test_should_retry_transient_4xx_returns_true(status):
    """408 timeout + 429 rate limit son transient → retry."""
    assert should_retry(status, error=None) is True


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_should_retry_2xx_returns_false(status):
    assert should_retry(status, error=None) is False


def test_should_retry_timeout_error_returns_true():
    """Timeout/Connection (no HTTP response) → transient retry."""
    assert should_retry(None, error="Request timed out") is True


def test_should_retry_connection_error_returns_true():
    assert should_retry(None, error="DNS resolution failed") is True


def test_should_retry_no_status_no_error_returns_true():
    """Defensive: si no hay status NI error, asumimos transient."""
    assert should_retry(None, error=None) is True


def test_non_retryable_codes_set():
    """D3: list debe ser {400, 401, 403, 404, 410, 422}."""
    assert NON_RETRYABLE_STATUS_CODES == frozenset({400, 401, 403, 404, 410, 422})


# --- compute_next_retry_at: backoff progression + jitter -----------------


def test_compute_next_retry_at_first_attempt_uses_first_backoff():
    backoff = [60, 300, 1800]
    with patch("sinpapel_webhooks.delivery.retry.random.uniform", return_value=1.0):
        before = timezone.now()
        result = compute_next_retry_at(1, backoff_list=backoff)
        delta = (result - before).total_seconds()
        assert 59 <= delta <= 61  # ~60s


def test_compute_next_retry_at_progresses_through_backoff():
    backoff = [60, 300, 1800, 7200, 43200]
    with patch("sinpapel_webhooks.delivery.retry.random.uniform", return_value=1.0):
        before = timezone.now()
        # attempts=2 → backoff[1] = 300
        result = compute_next_retry_at(2, backoff_list=backoff)
        delta = (result - before).total_seconds()
        assert 299 <= delta <= 301


def test_compute_next_retry_at_clamps_past_max_attempts():
    """Si attempts > len(backoff_list), usa último valor."""
    backoff = [60, 300, 1800]
    with patch("sinpapel_webhooks.delivery.retry.random.uniform", return_value=1.0):
        before = timezone.now()
        result = compute_next_retry_at(10, backoff_list=backoff)
        delta = (result - before).total_seconds()
        assert 1799 <= delta <= 1801  # backoff[-1] = 1800


def test_compute_next_retry_at_jitter_within_bounds():
    """Jitter ±10% — sample N runs, todos dentro de [base*0.9, base*1.1]."""
    backoff = [100]  # single base for clean check
    samples = [
        (compute_next_retry_at(1, backoff_list=backoff) - timezone.now()).total_seconds()
        for _ in range(50)
    ]
    # All samples within [90, 110] (base 100 with ±10% jitter)
    assert all(89 <= s <= 111 for s in samples), f"Out of bounds: min={min(samples)}, max={max(samples)}"


def test_compute_next_retry_at_attempts_below_one_clamps_to_one():
    """Defensive: attempts=0 → uses backoff[0]."""
    backoff = [60]
    with patch("sinpapel_webhooks.delivery.retry.random.uniform", return_value=1.0):
        before = timezone.now()
        result = compute_next_retry_at(0, backoff_list=backoff)
        delta = (result - before).total_seconds()
        assert 59 <= delta <= 61
