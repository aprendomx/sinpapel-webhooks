"""sinpapel-webhooks delivery layer (ADR-013).

Pluggable delivery backends:
- InlineBackend (S14.1): sync requests.post; no retry; dev/smoke only.
- OutboxBackend (S14.2): DB-backed queue + worker management command (default prod).
- CeleryBackend (S14.3): gated por extra `[celery]`; broker-based.

Factory: `get_delivery_backend()` resuelve backend desde
`settings.SINPAPEL_WEBHOOKS_BACKEND` (short-name o dotted-path).
"""
from __future__ import annotations
