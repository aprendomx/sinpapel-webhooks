"""Loose coupling test (S14.1 / T5).

Verifica que sinpapel core NO importa nada de sinpapel_webhooks (ADR-013
loose coupling pattern). El epic E14 debe ser removable sin tocar sinpapel
core — webhooks se conecta vía signal.connect a sinpapel models declarados
con sender="sinpapel.X" (string), nunca por import directo.

Los paquetes se localizan vía import (no por layout de repos hermanos en
disco), así el test corre igual en desarrollo local (installs editables) y
en CI (paquetes desde PyPI).
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

_PATTERN = re.compile(r"\bsinpapel_webhooks\b")
_SKIP_PARTS = {"__pycache__", ".venv", "venv", "docs", "site", "tests", "node_modules", ".git"}


def _package_dir(module_name: str) -> Path | None:
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        return None
    return Path(mod.__file__).resolve().parent  # type: ignore[arg-type]


def _offending_files(package_dir: Path) -> list[str]:
    offending: list[str] = []
    for py_file in package_dir.rglob("*.py"):
        if _SKIP_PARTS.intersection(py_file.parts):
            continue
        text = py_file.read_text(encoding="utf-8")
        if _PATTERN.search(text):
            offending.append(str(py_file))
    return offending


def test_sinpapel_core_does_not_import_sinpapel_webhooks():
    """sinpapel core code NO debe contener `import sinpapel_webhooks` ni
    `from sinpapel_webhooks ...` en ningún archivo .py."""
    core_dir = _package_dir("sinpapel")
    assert core_dir is not None, "sinpapel debe estar instalado (es dependencia)"

    offending = _offending_files(core_dir)
    assert not offending, (
        "sinpapel core importa sinpapel_webhooks (loose coupling violation):\n"
        + "\n".join(f"  - {p}" for p in offending)
    )


def test_sinpapel_drf_does_not_import_sinpapel_webhooks():
    """sinpapel_drf tampoco debe importar sinpapel_webhooks (S14.5 admin endpoints
    cambiará esto cuando se agreguen ViewSets sobre WebhookSubscription).

    En S14.1 confirmamos que el setup actual no acopla sinpapel_drf → webhooks.
    """
    drf_dir = _package_dir("sinpapel_drf")
    if drf_dir is None:
        return  # sinpapel_drf opcional

    offending = _offending_files(drf_dir)
    assert not offending, (
        "sinpapel_drf importa sinpapel_webhooks (S14.5 todavía no implementado):\n"
        + "\n".join(f"  - {p}" for p in offending)
    )
