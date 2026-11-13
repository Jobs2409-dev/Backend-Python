# backend_python/conftest.py
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from reclamos.models import AreaDependencia, Categoria, Estado, Rol

User = get_user_model()


@pytest.fixture(autouse=True)
def entorno_de_test(settings):
    """
    Aísla dependencias externas durante los tests:
    - Usa InMemoryChannelLayer en lugar de requerir un servidor Redis activo.
    """
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


@pytest.fixture
def roles(db):
    return {
        "ADMIN": Rol.objects.get_or_create(nombre="ADMIN")[0],
        "OPERADOR": Rol.objects.get_or_create(nombre="OPERADOR")[0],
        "VECINO": Rol.objects.get_or_create(nombre="VECINO")[0],
    }


@pytest.fixture
def admin_user(roles):
    return User.objects.create_user(
        username="admin_pytest",
        password="admin-password-123",
        rol=roles["ADMIN"],
    )


@pytest.fixture
def operador_user(roles):
    return User.objects.create_user(
        username="operador_pytest",
        password="operador-password-123",
        rol=roles["OPERADOR"],
    )


@pytest.fixture
def vecino_user(roles):
    return User.objects.create_user(
        username="vecino_pytest",
        password="vecino-password-123",
        rol=roles["VECINO"],
    )


@pytest.fixture
def dominio_base(db):
    area = AreaDependencia.objects.create(nombre="Obras y Servicios Públicos")
    categoria = Categoria.objects.create(nombre="Bacheo y Asfalto", area=area)
    pendiente = Estado.objects.get_or_create(nombre="Pendiente")[0]
    en_proceso = Estado.objects.get_or_create(nombre="En Proceso")[0]
    resuelto = Estado.objects.get_or_create(nombre="Resuelto")[0]
    return {
        "area": area,
        "categoria": categoria,
        "pendiente": pendiente,
        "en_proceso": en_proceso,
        "resuelto": resuelto,
    }


@pytest.fixture
def api_client():
    return APIClient()