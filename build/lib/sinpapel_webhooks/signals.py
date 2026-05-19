# sinpapel-webhooks — event-driven HTTP communication for sinpapel.
# Copyright (C) 2024-2026 Julio Adrián <jadrian.s@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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


# --- CondicionTransicion → workflow.predicate.configured ------------------


@receiver(post_save, sender="sinpapel.CondicionTransicion")
def on_condicion_transicion(sender: type[Model], instance: Model, created: bool, **kwargs: Any) -> None:
    """Emit workflow.predicate.configured on CondicionTransicion create/update."""
    payload: dict[str, Any] = {
        "condicion_id": instance.pk,
        "transicion_id": getattr(instance, "transicion_id", None),
        "tipo": getattr(instance, "tipo", None),
        "configuracion": getattr(instance, "configuracion", None) or {},
        "mensaje_error": getattr(instance, "mensaje_error", "") or "",
        "orden": getattr(instance, "orden", 0),
        "activo": bool(getattr(instance, "activo", False)),
        "action": "created" if created else "updated",
    }
    transaction.on_commit(
        lambda: emit_event("workflow.predicate.configured", payload, source=instance)
    )


# --- SLAConfiguracion → sla.configured ------------------------------------


@receiver(post_save, sender="sinpapel.SLAConfiguracion")
def on_sla_configuracion(sender: type[Model], instance: Model, created: bool, **kwargs: Any) -> None:
    """Emit sla.configured on SLAConfiguracion create/update."""
    payload: dict[str, Any] = {
        "sla_id": instance.pk,
        "estado_id": getattr(instance, "estado_id", None),
        "dias_maximos": getattr(instance, "dias_maximos", None),
        "accion_vencimiento": getattr(instance, "accion_vencimiento", None),
        "configuracion_accion": getattr(instance, "configuracion_accion", None) or {},
        "activo": bool(getattr(instance, "activo", False)),
        "action": "created" if created else "updated",
    }
    transaction.on_commit(
        lambda: emit_event("sla.configured", payload, source=instance)
    )


# --- Custom sinpapel signals (v0.5+) --------------------------------------
# Defensive import: tolerate older sinpapel versions without these signals.

try:
    from sinpapel.signals import (
        predicate_failed,
        sla_action_executed,
        sla_breached,
        transition_preview_requested,
    )
except ImportError:  # pragma: no cover — older sinpapel pin
    predicate_failed = None
    sla_breached = None
    sla_action_executed = None
    transition_preview_requested = None


def on_predicate_failed(sender: type[Model], target: Any, condicion: Any, user: Any, target_state: str, **kwargs: Any) -> None:
    """Receiver for sinpapel.signals.predicate_failed → emit workflow.predicate.failed."""
    target_ct = None
    target_id = None
    if target is not None:
        from django.contrib.contenttypes.models import ContentType
        target_ct = ContentType.objects.get_for_model(target).model
        target_id = getattr(target, "pk", None)

    payload: dict[str, Any] = {
        "condicion_id": getattr(condicion, "pk", None),
        "tipo": getattr(condicion, "tipo", None),
        "mensaje_error": getattr(condicion, "mensaje_error", "") or "",
        "transicion_id": getattr(condicion, "transicion_id", None),
        "target_object_id": target_id,
        "target_content_type": target_ct,
        "target_state": target_state,
        "user_id": _safe_user_id(user),
    }
    transaction.on_commit(
        lambda: emit_event("workflow.predicate.failed", payload, source=target)
    )


def on_sla_breached(sender: type[Model], target: Any, sla: Any, dias_transcurridos: int, **kwargs: Any) -> None:
    """Receiver for sinpapel.signals.sla_breached → emit sla.breached."""
    target_ct = None
    target_id = None
    if target is not None:
        from django.contrib.contenttypes.models import ContentType
        target_ct = ContentType.objects.get_for_model(target).model
        target_id = getattr(target, "pk", None)

    payload: dict[str, Any] = {
        "sla_id": getattr(sla, "pk", None),
        "estado": getattr(getattr(sla, "estado", None), "nombre", None),
        "dias_maximos": getattr(sla, "dias_maximos", None),
        "dias_transcurridos": dias_transcurridos,
        "target_object_id": target_id,
        "target_content_type": target_ct,
    }
    transaction.on_commit(
        lambda: emit_event("sla.breached", payload, source=target)
    )


def on_sla_action_executed(sender: type[Model], target: Any, sla: Any, accion: str, resultado: dict[str, Any], **kwargs: Any) -> None:
    """Receiver for sinpapel.signals.sla_action_executed → emit sla.action.executed."""
    target_ct = None
    target_id = None
    if target is not None:
        from django.contrib.contenttypes.models import ContentType
        target_ct = ContentType.objects.get_for_model(target).model
        target_id = getattr(target, "pk", None)

    payload: dict[str, Any] = {
        "sla_id": getattr(sla, "pk", None),
        "accion": accion,
        "configuracion_accion": getattr(sla, "configuracion_accion", None) or {},
        "resultado": resultado or {},
        "target_object_id": target_id,
        "target_content_type": target_ct,
    }
    transaction.on_commit(
        lambda: emit_event("sla.action.executed", payload, source=target)
    )


def on_transition_preview_requested(sender: type[Model], target: Any, target_state: str, user: Any, reporte: dict[str, Any], **kwargs: Any) -> None:
    """Receiver for sinpapel.signals.transition_preview_requested → emit workflow.transition.preview."""
    target_ct = None
    target_id = None
    if target is not None:
        from django.contrib.contenttypes.models import ContentType
        target_ct = ContentType.objects.get_for_model(target).model
        target_id = getattr(target, "pk", None)

    payload: dict[str, Any] = {
        "target_object_id": target_id,
        "target_content_type": target_ct,
        "target_state": target_state,
        "user_id": _safe_user_id(user),
        "permitido": bool(reporte.get("permitido", False)),
        "razones_bloqueo": reporte.get("razones_bloqueo", []),
        "side_effects": reporte.get("side_effects", []),
        "documentos_faltantes": reporte.get("documentos_faltantes", []),
        "predicados_fallidos": reporte.get("predicados_fallidos", []),
    }
    transaction.on_commit(
        lambda: emit_event("workflow.transition.preview", payload, source=target)
    )


if predicate_failed is not None:
    predicate_failed.connect(on_predicate_failed, dispatch_uid="sinpapel_webhooks.on_predicate_failed")
    sla_breached.connect(on_sla_breached, dispatch_uid="sinpapel_webhooks.on_sla_breached")
    sla_action_executed.connect(on_sla_action_executed, dispatch_uid="sinpapel_webhooks.on_sla_action_executed")
    transition_preview_requested.connect(on_transition_preview_requested, dispatch_uid="sinpapel_webhooks.on_transition_preview_requested")
