# backend_python/reclamos/tests/test_graphql.py
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from reclamos.models import AreaDependencia, Categoria, Estado, Reclamo, Rol

User = get_user_model()


class GraphQLClase11Tests(APITestCase):
    def setUp(self):
        self.operator_role = Rol.objects.create(nombre='OPERADOR')
        self.neighbor_role = Rol.objects.create(nombre='VECINO')

        self.operator = User.objects.create_user(
            username='operador_gql',
            password='operator-password',
            rol=self.operator_role
        )
        self.neighbor_1 = User.objects.create_user(
            username='vecino1_gql',
            password='neighbor-password',
            rol=self.neighbor_role
        )
        self.neighbor_2 = User.objects.create_user(
            username='vecino2_gql',
            password='neighbor-password',
            rol=self.neighbor_role
        )

        self.area = AreaDependencia.objects.create(nombre='Espacios Verdes')
        self.categoria = Categoria.objects.create(nombre='Poda de árboles', area=self.area)
        self.estado_pendiente = Estado.objects.create(nombre='Pendiente')
        self.estado_proceso = Estado.objects.create(nombre='En Proceso')

        self.reclamo_v1 = Reclamo.objects.create(
            titulo='Rama caída en vereda',
            descripcion='Hay una rama bloqueando el paso peatonal.',
            usuario=self.neighbor_1,
            categoria=self.categoria,
            estado_actual=self.estado_pendiente,
        )
        self.reclamo_v2 = Reclamo.objects.create(
            titulo='Plaza sin iluminación',
            descripcion='Faltan focos en la plaza principal del barrio.',
            usuario=self.neighbor_2,
            categoria=self.categoria,
            estado_actual=self.estado_pendiente,
        )

    def _auth_header(self, user):
        token = str(AccessToken.for_user(user))
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_mis_reclamos_filters_by_owner_and_role(self):
        query = """
        query {
            misReclamos {
                id
                titulo
                estadoActual { nombre }
            }
        }
        """
        res_v1 = self.client.post(
            "/graphql/",
            {"query": query},
            format="json",
            **self._auth_header(self.neighbor_1),
        )
        self.assertEqual(res_v1.status_code, 200)
        data_v1 = res_v1.json()["data"]["misReclamos"]
        self.assertEqual(len(data_v1), 1)
        self.assertEqual(data_v1[0]["titulo"], "Rama caída en vereda")

        res_op = self.client.post(
            "/graphql/",
            {"query": query},
            format="json",
            **self._auth_header(self.operator),
        )
        self.assertEqual(res_op.status_code, 200)
        data_op = res_op.json()["data"]["misReclamos"]
        self.assertEqual(len(data_op), 2)

    def test_crear_reclamo_mutation_sanitizes_xss_and_creates_record(self):
        mutation = """
        mutation ($titulo: String!, $descripcion: String!, $categoriaId: ID!) {
            crearReclamo(titulo: $titulo, descripcion: $descripcion, categoriaId: $categoriaId) {
                ok
                reclamo {
                    id
                    titulo
                    descripcion
                    estadoActual { nombre }
                }
            }
        }
        """
        variables = {
            "titulo": "Bache peligroso <script>alert(1)</script>",
            "descripcion": "Pozo profundo en esquina principal <b>urgente</b>.",
            "categoriaId": str(self.categoria.id),
        }
        res = self.client.post(
            "/graphql/",
            {"query": mutation, "variables": variables},
            format="json",
            **self._auth_header(self.neighbor_1),
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["data"]["crearReclamo"]
        self.assertTrue(payload["ok"])
        self.assertNotIn("<script>", payload["reclamo"]["titulo"])
        self.assertEqual(payload["reclamo"]["estadoActual"]["nombre"], "Pendiente")

    def test_cambiar_estado_mutation_enforces_rbac(self):
        mutation = """
        mutation ($reclamoId: ID!, $nuevoEstadoId: ID!, $observacion: String!) {
            cambiarEstadoReclamo(
                reclamoId: $reclamoId,
                nuevoEstadoId: $nuevoEstadoId,
                observacion: $observacion
            ) {
                ok
                reclamo {
                    estadoActual { nombre }
                }
            }
        }
        """
        variables = {
            "reclamoId": str(self.reclamo_v1.id),
            "nuevoEstadoId": str(self.estado_proceso.id),
            "observacion": "Cuadrilla asignada para revisión.",
        }

        res_v1 = self.client.post(
            "/graphql/",
            {"query": mutation, "variables": variables},
            format="json",
            **self._auth_header(self.neighbor_1),
        )
        self.assertIn("errors", res_v1.json())

        res_op = self.client.post(
            "/graphql/",
            {"query": mutation, "variables": variables},
            format="json",
            **self._auth_header(self.operator),
        )
        self.assertEqual(res_op.status_code, 200)
        self.assertTrue(res_op.json()["data"]["cambiarEstadoReclamo"]["ok"])
        self.assertEqual(
            res_op.json()["data"]["cambiarEstadoReclamo"]["reclamo"]["estadoActual"]["nombre"],
            "En Proceso",
        )