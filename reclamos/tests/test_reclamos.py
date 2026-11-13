# backend_python/reclamos/tests/test_reclamos.py
import pytest
from django.core.exceptions import ValidationError

from reclamos.models import Reclamo, RegistroHistorial, SecurityLog
from reclamos.services import ReclamoService


@pytest.mark.django_db
def test_health_check_endpoint(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_vecino_crea_reclamo_y_genera_historial_y_auditoria(api_client, vecino_user, dominio_base):
    api_client.force_authenticate(user=vecino_user)
    payload = {
        "titulo": "Caño roto en calle Mitre",
        "descripcion": "Pérdida importante de agua potable en la esquina.",
        "categoria": dominio_base["categoria"].id,
    }

    response = api_client.post("/api/reclamos/", payload, format="json")

    assert response.status_code == 201
    reclamo = Reclamo.objects.get(titulo="Caño roto en calle Mitre")
    assert reclamo.estado_actual == dominio_base["pendiente"]
    assert RegistroHistorial.objects.filter(reclamo=reclamo).count() == 1
    assert SecurityLog.objects.filter(user=vecino_user, action="RECLAMO_CREADO").exists()


@pytest.mark.django_db
def test_vecino_no_puede_cambiar_estado_de_reclamo(api_client, vecino_user, dominio_base):
    reclamo = ReclamoService.crear_reclamo(
        usuario=vecino_user,
        titulo="Bache profundo",
        descripcion="Bache peligroso frente a la escuela.",
        categoria_id=dominio_base["categoria"].id,
    )

    api_client.force_authenticate(user=vecino_user)
    response = api_client.patch(
        f"/api/reclamos/{reclamo.id}/cambiar_estado/",
        {"nuevo_estado_id": dominio_base["en_proceso"].id, "observacion": "Intento no autorizado"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_operador_cambia_estado_y_falla_si_repite_mismo_estado(operador_user, vecino_user, dominio_base):
    reclamo = ReclamoService.crear_reclamo(
        usuario=vecino_user,
        titulo="Vereda hundida",
        descripcion="Baldosas rotas que impiden el paso.",
        categoria_id=dominio_base["categoria"].id,
    )

    actualizado = ReclamoService.cambiar_estado(
        reclamo_id=reclamo.id,
        nuevo_estado_id=dominio_base["en_proceso"].id,
        operador=operador_user,
        observacion="Personal técnico asignado.",
    )
    assert actualizado.estado_actual == dominio_base["en_proceso"]

    with pytest.raises(ValidationError):
        ReclamoService.cambiar_estado(
            reclamo_id=reclamo.id,
            nuevo_estado_id=dominio_base["en_proceso"].id,
            operador=operador_user,
            observacion="Repetir el mismo estado debe fallar.",
        )