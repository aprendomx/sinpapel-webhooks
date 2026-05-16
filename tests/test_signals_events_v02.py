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
