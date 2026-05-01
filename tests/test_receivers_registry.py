"""Receiver registry tests (S14.4 / T1).

Verifies InboundReceiverRegistry classvar singleton + @webhook_receiver
decorator + register/get/duplicate/clear/all_keys API.
"""
from __future__ import annotations

import pytest

from sinpapel_webhooks.receivers.registry import (
    InboundReceiverRegistry,
    webhook_receiver,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Autouse: reset registry state pre/post test (singleton classvar)."""
    InboundReceiverRegistry.clear()
    yield
    InboundReceiverRegistry.clear()


# --- register/get ---------------------------------------------------------


def test_register_and_get_handler():
    def handler(payload, request):
        return {"acked": True}

    InboundReceiverRegistry.register("baz", "payment.confirmed", handler)
    assert InboundReceiverRegistry.get("baz", "payment.confirmed") is handler


def test_get_returns_none_for_missing():
    assert InboundReceiverRegistry.get("nonexistent", "event") is None


def test_register_duplicate_raises_value_error():
    def handler1(payload, request): pass
    def handler2(payload, request): pass

    InboundReceiverRegistry.register("baz", "payment.confirmed", handler1)
    with pytest.raises(ValueError, match="Duplicate receiver for baz/payment.confirmed"):
        InboundReceiverRegistry.register("baz", "payment.confirmed", handler2)


# --- @webhook_receiver decorator -----------------------------------------


def test_decorator_registers_handler():
    @webhook_receiver(source="moneygram", event="dispersion.completed")
    def handler(payload, request):
        return None

    registered = InboundReceiverRegistry.get("moneygram", "dispersion.completed")
    assert registered is handler


def test_decorator_returns_original_function():
    """Decorator NO debe wrappear la función — debe retornar la misma callable."""
    @webhook_receiver(source="test", event="ping")
    def handler(payload, request):
        return {"x": 1}

    # Function callable directamente
    result = handler({}, None)
    assert result == {"x": 1}


def test_decorator_duplicate_raises():
    """Decorator usage también respeta no-duplicate constraint."""
    @webhook_receiver(source="dup_test", event="evt")
    def handler1(payload, request): pass

    with pytest.raises(ValueError, match="Duplicate receiver"):
        @webhook_receiver(source="dup_test", event="evt")
        def handler2(payload, request): pass


# --- all_keys + clear ---------------------------------------------------


def test_all_keys_returns_registered_pairs():
    def h1(p, r): pass
    def h2(p, r): pass

    InboundReceiverRegistry.register("a", "evt1", h1)
    InboundReceiverRegistry.register("b", "evt2", h2)

    keys = InboundReceiverRegistry.all_keys()
    assert ("a", "evt1") in keys
    assert ("b", "evt2") in keys
    assert len(keys) == 2


def test_clear_resets_state():
    InboundReceiverRegistry.register("test", "evt", lambda p, r: None)
    assert InboundReceiverRegistry.all_keys() == [("test", "evt")]

    InboundReceiverRegistry.clear()
    assert InboundReceiverRegistry.all_keys() == []


# --- Top-level re-export (sinpapel_webhooks public API) ------------------


def test_webhook_receiver_importable_from_top_level():
    """`from sinpapel_webhooks import webhook_receiver` debe funcionar."""
    from sinpapel_webhooks import webhook_receiver as wr_top
    assert wr_top is webhook_receiver
