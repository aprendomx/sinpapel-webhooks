"""Tests for v0.2.0 event types (predicates, SLA, preview, metadata)."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.django_db(transaction=True)
def test_condicion_transicion_create_emits_predicate_configured():
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo
    from sinpapel.models.predicates import CondicionTransicion
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="s", url="https://x.test/h",
        events=["workflow.predicate.configured"],
        secret="s", active=True,
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        e_a = Estado.objects.create(nombre="A")
        e_b = Estado.objects.create(nombre="B")
        flujo = VersionFlujo.objects.create(nombre="F", activo=True)
        config_t = ConfiguracionTransicion.objects.create(
            flujo=flujo, estado_origen=e_a, estado_destino=e_b,
        )
        CondicionTransicion.objects.create(
            transicion=config_t,
            tipo="json_logic",
            configuracion={"rule": {"==": [1, 1]}},
            mensaje_error="ok",
            activo=True,
        )

    events = WebhookEvent.objects.filter(event_type="workflow.predicate.configured")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["tipo"] == "json_logic"
    assert payload["activo"] is True
    assert payload["action"] == "created"


@pytest.mark.django_db(transaction=True)
def test_sla_configuracion_create_emits_sla_configured():
    from sinpapel.models import Estado
    from sinpapel.models.sla import SLAConfiguracion
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="s", url="https://x.test/h",
        events=["sla.configured"],
        secret="s", active=True,
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        estado = Estado.objects.create(nombre="EN_REV")
        SLAConfiguracion.objects.create(
            estado=estado,
            dias_maximos=3,
            accion_vencimiento="notificar",
            configuracion_accion={"grupo_id": 1},
            activo=True,
        )

    events = WebhookEvent.objects.filter(event_type="sla.configured")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["dias_maximos"] == 3
    assert payload["accion_vencimiento"] == "notificar"
    assert payload["action"] == "created"


@pytest.mark.django_db(transaction=True)
def test_predicate_failed_signal_emits_workflow_predicate_failed():
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo
    from sinpapel.models.predicates import CondicionTransicion
    from sinpapel.signals import predicate_failed
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="s", url="https://x.test/h",
        events=["workflow.predicate.failed"], secret="s", active=True,
    )

    e_a = Estado.objects.create(nombre="A2")
    e_b = Estado.objects.create(nombre="B2")
    flujo = VersionFlujo.objects.create(nombre="F2-PF", activo=True)
    config_t = ConfiguracionTransicion.objects.create(
        flujo=flujo, estado_origen=e_a, estado_destino=e_b,
    )
    condicion = CondicionTransicion.objects.create(
        transicion=config_t,
        tipo="json_logic",
        configuracion={"rule": {"==": [1, 2]}},
        mensaje_error="bloqueo",
        activo=True,
    )

    # Use Subscription as opaque target.
    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        predicate_failed.send_robust(
            sender=type(target),
            target=target,
            condicion=condicion,
            user=None,
            target_state="B2",
        )

    events = WebhookEvent.objects.filter(event_type="workflow.predicate.failed")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["target_state"] == "B2"
    assert payload["mensaje_error"] == "bloqueo"
    assert payload["condicion_id"] == condicion.id


@pytest.mark.django_db(transaction=True)
def test_sla_breached_signal_emits_sla_breached_event():
    from sinpapel.models import Estado
    from sinpapel.models.sla import SLAConfiguracion
    from sinpapel.signals import sla_breached
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="s", url="https://x.test/h",
        events=["sla.breached"], secret="s", active=True,
    )

    estado = Estado.objects.create(nombre="EN_REV_SLA_X")
    sla = SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=2,
        accion_vencimiento="alertar",
        configuracion_accion={"campo": "alerta", "valor": True},
        activo=True,
    )
    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        sla_breached.send_robust(
            sender=type(target),
            target=target,
            sla=sla,
            dias_transcurridos=7,
        )

    events = WebhookEvent.objects.filter(event_type="sla.breached")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["sla_id"] == sla.pk
    assert payload["dias_transcurridos"] == 7
    assert payload["dias_maximos"] == 2


@pytest.mark.django_db(transaction=True)
def test_sla_action_executed_signal_emits_event():
    from sinpapel.models import Estado
    from sinpapel.models.sla import SLAConfiguracion
    from sinpapel.signals import sla_action_executed
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="s", url="https://x.test/h",
        events=["sla.action.executed"], secret="s", active=True,
    )

    estado = Estado.objects.create(nombre="EN_REV_SLA_Y")
    sla = SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=2,
        accion_vencimiento="notificar",
        configuracion_accion={"grupo_id": 1},
        activo=True,
    )
    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        sla_action_executed.send_robust(
            sender=type(target),
            target=target,
            sla=sla,
            accion="notificar",
            resultado={"accion": "notificar", "grupo": "ops"},
        )

    events = WebhookEvent.objects.filter(event_type="sla.action.executed")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["accion"] == "notificar"
    assert payload["resultado"]["grupo"] == "ops"


@pytest.mark.django_db(transaction=True)
def test_transition_preview_signal_emits_event():
    from sinpapel.signals import transition_preview_requested
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="s", url="https://x.test/h",
        events=["workflow.transition.preview"], secret="s", active=True,
    )

    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )
    reporte = {
        "permitido": False,
        "razones_bloqueo": [{"tipo": "predicado", "mensaje": "x"}],
        "side_effects": [],
        "documentos_faltantes": [],
        "predicados_fallidos": [{"condicion_id": 1, "tipo": "json_logic", "mensaje": "x"}],
        "aprobadores_requeridos": [],
        "historial_reciente": [],
    }

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        transition_preview_requested.send_robust(
            sender=type(target),
            target=target,
            target_state="B-prev",
            user=None,
            reporte=reporte,
        )

    events = WebhookEvent.objects.filter(event_type="workflow.transition.preview")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["permitido"] is False
    assert payload["target_state"] == "B-prev"
    assert payload["predicados_fallidos"][0]["condicion_id"] == 1
