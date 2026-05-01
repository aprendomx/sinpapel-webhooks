"""Inbound receiver registry (S14.4 / T1, D2).

Classvar singleton dict (`_receivers: dict[(source, event), Callable]`) +
`@webhook_receiver(source, event)` decorator que registra handlers en startup
via Django `autodiscover_modules("webhooks")` (configurado en apps.ready).

Thread-safe sufficient para Django request-response cycle (no concurrent
modification durante request handling; registration happens at startup only).
"""
from __future__ import annotations

from typing import Callable


class InboundReceiverRegistry:
    """Singleton registry para inbound webhook handlers.

    Keyed por `(source, event_type)` tuple. Source = nombre del servicio
    externo (e.g. "baz", "moneygram"); event_type = tipo de evento (e.g.
    "payment.confirmed", "dispersion.completed").
    """

    _receivers: dict[tuple[str, str], Callable] = {}

    @classmethod
    def register(cls, source: str, event: str, handler: Callable) -> None:
        """Registra handler para (source, event). Raises ValueError on duplicate."""
        key = (source, event)
        if key in cls._receivers:
            raise ValueError(
                f"Duplicate receiver for {source}/{event}: "
                f"already registered as {cls._receivers[key].__qualname__}"
            )
        cls._receivers[key] = handler

    @classmethod
    def get(cls, source: str, event: str) -> Callable | None:
        """Lookup handler. Returns None si no registered."""
        return cls._receivers.get((source, event))

    @classmethod
    def all_keys(cls) -> list[tuple[str, str]]:
        """Returns lista de (source, event) registered. Útil para admin/debug."""
        return list(cls._receivers.keys())

    @classmethod
    def clear(cls) -> None:
        """Reset state. Para tests; NO usar en producción."""
        cls._receivers = {}


def webhook_receiver(*, source: str, event: str) -> Callable[[Callable], Callable]:
    """Decorator: registra handler en InboundReceiverRegistry.

    Usage:
        @webhook_receiver(source="baz", event="payment.confirmed")
        def handle_baz_payment(payload: dict, request) -> dict | None:
            ...

    Args:
        source: nombre del servicio externo (e.g. "baz", "moneygram").
        event: tipo de evento (e.g. "payment.confirmed").

    Returns:
        Decorator que registra el handler y retorna la función sin modificar.
    """
    def decorator(func: Callable) -> Callable:
        InboundReceiverRegistry.register(source, event, func)
        return func
    return decorator
