"""Loose coupling test (S14.1 / T5).

Verifica que sinpapel core NO importa nada de sinpapel_webhooks (ADR-013
loose coupling pattern). El epic E14 debe ser removable sin tocar sinpapel
core — webhooks se conecta vía signal.connect a sinpapel models declarados
con sender="sinpapel.X" (string), nunca por import directo.
"""
from __future__ import annotations

import re
from pathlib import Path


def test_sinpapel_core_does_not_import_sinpapel_webhooks():
    """sinpapel core code NO debe contener `import sinpapel_webhooks` ni
    `from sinpapel_webhooks ...` en ningún archivo .py."""
    project_root = Path(__file__).resolve().parents[2]
    sinpapel_dir = project_root / "sinpapel"

    assert sinpapel_dir.exists(), f"sinpapel dir not found at {sinpapel_dir}"

    # Buscar referencias a sinpapel_webhooks en .py files (excluir .pyc, __pycache__)
    pattern = re.compile(r"\bsinpapel_webhooks\b")
    offending: list[str] = []

    for py_file in sinpapel_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8")
        if pattern.search(text):
            offending.append(str(py_file.relative_to(project_root)))

    assert not offending, (
        f"sinpapel core importa sinpapel_webhooks (loose coupling violation):\n"
        + "\n".join(f"  - {p}" for p in offending)
    )


def test_sinpapel_drf_does_not_import_sinpapel_webhooks():
    """sinpapel_drf tampoco debe importar sinpapel_webhooks (S14.5 admin endpoints
    cambiará esto cuando se agreguen ViewSets sobre WebhookSubscription).

    En S14.1 confirmamos que el setup actual no acopla sinpapel_drf → webhooks.
    """
    project_root = Path(__file__).resolve().parents[2]
    drf_dir = project_root / "sinpapel_drf"

    if not drf_dir.exists():
        return  # sinpapel_drf opcional

    pattern = re.compile(r"\bsinpapel_webhooks\b")
    offending: list[str] = []

    for py_file in drf_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8")
        if pattern.search(text):
            offending.append(str(py_file.relative_to(project_root)))

    assert not offending, (
        f"sinpapel_drf importa sinpapel_webhooks (S14.5 todavía no implementado):\n"
        + "\n".join(f"  - {p}" for p in offending)
    )
