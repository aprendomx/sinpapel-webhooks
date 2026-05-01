"""Signal handlers — sinpapel domain events → emit_event.

Loose coupling: sinpapel core NO importa nada de sinpapel-webhooks.
Estos handlers son conectados desde `apps.py:ready()` vía import side-effect.

S14.1 events emitidos (walking skeleton — solo create paths):
- workflow.transition.completed: SeguimientoWorkflow created (transitions exitosas
  ya generaron el row; failed transitions raise excepción y no llegan acá).
- signature.completed: RegistroFirma created.
- document.uploaded: InstanciaDocumento created.

Eventos additional (.rejected/.failed/.approved) llegan en S14.2+ cuando se
agreguen state tracking o consumer-explicit emit calls.

D2: snapshot payload AHORA (sync), pasar al lambda transaction.on_commit.
D6: defensive getattr(instance, attr, None) — tolera schema evolution.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .emit import emit_event


def _safe_state_name(state: Any) -> str | None:
    """Extrae state.nombre defensively (state puede ser None)."""
    if state is None:
        return None
    return getattr(state, "nombre", None)


def _safe_user_id(user: Any) -> int | None:
    if user is None:
        return None
    return getattr(user, "pk", None) or getattr(user, "id", None)


# --- SeguimientoWorkflow → workflow.transition.completed ------------------


@receiver(post_save, sender="sinpapel.SeguimientoWorkflow")
def on_seguimiento_workflow(sender: type[Model], instance: Model, created: bool, **kwargs: Any) -> None:
    """Emit workflow.transition.completed cuando se persiste un SeguimientoWorkflow.

    Solo emit en create — updates de SeguimientoWorkflow son raros y no
    representan nuevas transitions.
    """
    if not created:
        return

    # D2: snapshot dict NOW (sync), pasar al lambda
    payload: dict[str, Any] = {
        "seguimiento_id": instance.pk,
        "estado_anterior": _safe_state_name(getattr(instance, "estado_anterior", None)),
        "estado_nuevo": _safe_state_name(getattr(instance, "estado_nuevo", None)),
        "user_id": _safe_user_id(getattr(instance, "usuario_accion", None)),
        "comentarios": getattr(instance, "comentarios", "") or "",
        "fecha_accion": (
            instance.fecha_accion.isoformat()
            if getattr(instance, "fecha_accion", None)
            else None
        ),
        # GFK al target (Solicitud, RegistroAT, etc.)
        "target_object_id": getattr(instance, "target_object_id", None),
        "target_content_type": (
            getattr(instance.target_content_type, "model", None)
            if getattr(instance, "target_content_type", None)
            else None
        ),
    }
    transaction.on_commit(
        lambda: emit_event("workflow.transition.completed", payload, source=instance)
    )


# --- RegistroFirma → signature.completed ----------------------------------


@receiver(post_save, sender="sinpapel.RegistroFirma")
def on_registro_firma(sender: type[Model], instance: Model, created: bool, **kwargs: Any) -> None:
    """Emit signature.completed cuando se crea un RegistroFirma.

    Failed signatures: el RegistroFirma puede tener verification_result="FAILED";
    para S14.1 walking skeleton emitimos solo en create. Eventos .failed llegarán
    en S14.2+ con state-change tracking.
    """
    if not created:
        return

    payload: dict[str, Any] = {
        "registro_firma_id": instance.pk,
        "backend_name": getattr(instance, "backend_name", None),
        "signer_id": _safe_user_id(getattr(instance, "signer", None)),
        "signer_display_name": getattr(instance, "signer_display_name", "") or "",
        "verification_result": getattr(instance, "verification_result", None),
        "is_required": bool(getattr(instance, "is_required", False)),
        "content_hash": getattr(instance, "content_hash", "") or "",
        "signed_at": (
            instance.signed_at.isoformat()
            if getattr(instance, "signed_at", None)
            else None
        ),
        "target_object_id": getattr(instance, "target_object_id", None),
        "target_content_type": (
            getattr(instance.target_content_type, "model", None)
            if getattr(instance, "target_content_type", None)
            else None
        ),
    }
    transaction.on_commit(
        lambda: emit_event("signature.completed", payload, source=instance)
    )


# --- InstanciaDocumento → document.uploaded -------------------------------


@receiver(post_save, sender="sinpapel.InstanciaDocumento")
def on_instancia_documento(sender: type[Model], instance: Model, created: bool, **kwargs: Any) -> None:
    """Emit document.uploaded cuando se crea un InstanciaDocumento.

    document.approved / document.rejected requieren state-change tracking que no
    está en S14.1 walking skeleton — llegan en S14.2+ o consumer-explicit emits.
    """
    if not created:
        return

    payload: dict[str, Any] = {
        "instancia_documento_id": instance.pk,
        "documento_id": getattr(instance, "documento_id", None),
        "target_object_id": getattr(instance, "target_object_id", None),
        "target_content_type": (
            getattr(instance.target_content_type, "model", None)
            if getattr(instance, "target_content_type", None)
            else None
        ),
        "actor_object_id": getattr(instance, "actor_object_id", None),
        "actor_content_type": (
            getattr(instance.actor_content_type, "model", None)
            if getattr(instance, "actor_content_type", None)
            else None
        ),
        "metadatos": getattr(instance, "metadatos", None) or {},
    }
    transaction.on_commit(
        lambda: emit_event("document.uploaded", payload, source=instance)
    )
