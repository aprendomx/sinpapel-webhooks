"""Signal handlers tests (S14.1 / T4).

Verifies post_save → emit_event invocation post-commit, snapshot pattern,
defensive getattr, bulk_create no-signal caveat.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


@pytest.fixture
def user(db):
    return User.objects.create_user(username="signal-test-user", password="x")  # noqa: S106


# --- SeguimientoWorkflow signal ------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_seguimiento_workflow_create_emits_workflow_transition_completed(user):
    """Crear SeguimientoWorkflow → emit workflow.transition.completed post-commit."""
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow
    from sinpapel_webhooks.models import WebhookSubscription

    # Estados mínimos para FK
    e_anterior = Estado.objects.create(nombre="ANTES")
    e_nuevo = Estado.objects.create(nombre="DESPUES")

    # Subscription matching
    WebhookSubscription.objects.create(
        name="sub", url="https://example.test/hook",
        events=["workflow.transition.completed"],
        secret="secret", active=True,
    )

    with patch("sinpapel_webhooks.emit.get_delivery_backend") as mock_factory:
        # Necesita un target — usamos el Subscription mismo como GFK target
        target = WebhookSubscription.objects.create(
            name="target", url="https://t.test/h", events=[], secret="s",
        )
        target_ct = ContentType.objects.get_for_model(target)

        SeguimientoWorkflow.objects.create(
            target_content_type=target_ct,
            target_object_id=target.pk,
            estado_anterior=e_anterior,
            estado_nuevo=e_nuevo,
            usuario_accion=user,
            comentarios="test transition",
        )

        # Post-commit: el lambda en transaction.on_commit ejecutó
        # Importamos aquí para verificar contadores post-emit
        from sinpapel_webhooks.models import WebhookEvent
        events = WebhookEvent.objects.filter(event_type="workflow.transition.completed")
        assert events.count() == 1
        event = events.first()
        assert event.payload["estado_anterior"] == "ANTES"
        assert event.payload["estado_nuevo"] == "DESPUES"
        assert event.payload["comentarios"] == "test transition"

        # Backend invoked
        assert mock_factory.return_value.enqueue.called


@pytest.mark.django_db(transaction=True)
def test_seguimiento_workflow_update_does_not_emit(user):
    """Update de SeguimientoWorkflow (created=False) → NO emit."""
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    e1 = Estado.objects.create(nombre="A")
    e2 = Estado.objects.create(nombre="B")
    WebhookSubscription.objects.create(
        name="sub", url="https://x.test/h",
        events=["workflow.transition.completed"], secret="s", active=True,
    )

    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        sw = SeguimientoWorkflow.objects.create(
            target_content_type=target_ct, target_object_id=target.pk,
            estado_anterior=e1, estado_nuevo=e2, usuario_accion=user,
        )
        events_after_create = WebhookEvent.objects.filter(
            event_type="workflow.transition.completed"
        ).count()

        # Update
        sw.comentarios = "updated"
        sw.save()

        events_after_update = WebhookEvent.objects.filter(
            event_type="workflow.transition.completed"
        ).count()
        assert events_after_create == events_after_update == 1


# --- RegistroFirma signal -------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_registro_firma_create_emits_signature_completed():
    from sinpapel.models.signatures import RegistroFirma
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="firma-sub", url="https://x.test/h",
        events=["signature.completed"], secret="s", active=True,
    )

    target = WebhookSubscription.objects.create(
        name="firma-target", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        RegistroFirma.objects.create(
            backend_name="fake",
            signer_display_name="Test Signer",
            target_content_type=target_ct,
            target_object_id=target.pk,
            content_hash="abc123",
            verification_result="VALID",
            signed_at=timezone.now(),
        )

        events = WebhookEvent.objects.filter(event_type="signature.completed")
        assert events.count() == 1
        event = events.first()
        assert event.payload["backend_name"] == "fake"
        assert event.payload["verification_result"] == "VALID"


# --- InstanciaDocumento signal --------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_instancia_documento_create_emits_document_uploaded():
    from sinpapel.models.documents import InstanciaDocumento
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="doc-sub", url="https://x.test/h",
        events=["document.uploaded"], secret="s", active=True,
    )

    target = WebhookSubscription.objects.create(
        name="doc-target", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    actor_ct = ContentType.objects.get_for_model(target)  # reuse

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        InstanciaDocumento.objects.create(
            target_content_type=target_ct,
            target_object_id=target.pk,
            actor_content_type=actor_ct,
            actor_object_id=target.pk,
        )

        events = WebhookEvent.objects.filter(event_type="document.uploaded")
        assert events.count() == 1


# --- bulk_create caveat (Django std behavior) ----------------------------


@pytest.mark.django_db(transaction=True)
def test_bulk_create_does_not_emit_signals(user):
    """Documentar: bulk_create() bypasses post_save signals (Django std behavior).

    Consumer debe usar .save() iterativo si necesita signals + webhooks.
    Esta limitation se documenta en README S14.6.
    """
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="sub", url="https://x.test/h",
        events=["workflow.transition.completed"], secret="s", active=True,
    )

    e1 = Estado.objects.create(nombre="A")
    e2 = Estado.objects.create(nombre="B")
    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        SeguimientoWorkflow.objects.bulk_create([
            SeguimientoWorkflow(
                target_content_type=target_ct, target_object_id=target.pk,
                estado_anterior=e1, estado_nuevo=e2, usuario_accion=user,
            ),
            SeguimientoWorkflow(
                target_content_type=target_ct, target_object_id=target.pk,
                estado_anterior=e1, estado_nuevo=e2, usuario_accion=user,
            ),
        ])

        events = WebhookEvent.objects.filter(event_type="workflow.transition.completed")
        # bulk_create NO dispara signals → 0 events
        assert events.count() == 0


# --- Snapshot pattern (D2) -----------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_signal_snapshot_pattern_payload_stable(user):
    """Mutación post-signal NO debe afectar payload (D2 snapshot pattern).

    Si signal handler captura instance por reference y el caller muta el
    instance entre signal fire y on_commit, payload reflejaría la mutación.
    Snapshot pattern previene esto.
    """
    from sinpapel.models.workflow import Estado, SeguimientoWorkflow
    from sinpapel_webhooks.models import WebhookEvent, WebhookSubscription

    WebhookSubscription.objects.create(
        name="sub", url="https://x.test/h",
        events=["workflow.transition.completed"], secret="s", active=True,
    )

    e1 = Estado.objects.create(nombre="ORIG_ANTES")
    e2 = Estado.objects.create(nombre="ORIG_DESPUES")
    target = WebhookSubscription.objects.create(
        name="t", url="https://t.test/h", events=[], secret="s",
    )
    target_ct = ContentType.objects.get_for_model(target)

    with patch("sinpapel_webhooks.emit.get_delivery_backend"):
        sw = SeguimientoWorkflow.objects.create(
            target_content_type=target_ct, target_object_id=target.pk,
            estado_anterior=e1, estado_nuevo=e2, usuario_accion=user,
            comentarios="ORIGINAL",
        )

        # In-memory mutation pre-commit (no save) — payload should NOT change
        sw.comentarios = "MUTATED_AFTER_SIGNAL"

    event = WebhookEvent.objects.get(event_type="workflow.transition.completed")
    assert event.payload["comentarios"] == "ORIGINAL"  # snapshot preserved
