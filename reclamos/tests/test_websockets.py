# backend_python/reclamos/tests/test_websockets.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken

from VozVecinal.asgi import application
from reclamos.models import AreaDependencia, Categoria, Estado, Rol
from reclamos.services import ReclamoService

User = get_user_model()


class WebSocketClase10Tests(TransactionTestCase):
    def setUp(self):
        self.admin_role = Rol.objects.create(nombre='ADMIN')
        self.operator_role = Rol.objects.create(nombre='OPERADOR')
        self.neighbor_role = Rol.objects.create(nombre='VECINO')

        self.operator = User.objects.create_user(
            username='operador_ws',
            password='operator-password',
            rol=self.operator_role
        )
        self.neighbor = User.objects.create_user(
            username='vecino_ws',
            password='neighbor-password',
            rol=self.neighbor_role
        )

        self.area = AreaDependencia.objects.create(nombre='Obras Públicas')
        self.categoria = Categoria.objects.create(nombre='Alumbrado', area=self.area)
        self.estado_pendiente = Estado.objects.create(nombre='Pendiente')

    async def test_public_websocket_allows_anonymous_connection(self):
        communicator = WebsocketCommunicator(application, "/ws/reclamos/publicos/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_category_websocket_rejects_anonymous_and_neighbor(self):
        comm_anon = WebsocketCommunicator(application, f"/ws/reclamos/{self.categoria.id}/")
        connected_anon, _ = await comm_anon.connect()
        self.assertFalse(connected_anon)

        neighbor_token = str(AccessToken.for_user(self.neighbor))
        comm_neighbor = WebsocketCommunicator(
            application,
            f"/ws/reclamos/{self.categoria.id}/?token={neighbor_token}"
        )
        connected_neighbor, _ = await comm_neighbor.connect()
        self.assertFalse(connected_neighbor)

    async def test_category_websocket_accepts_operator_and_sends_presence(self):
        operator_token = str(AccessToken.for_user(self.operator))
        communicator = WebsocketCommunicator(
            application,
            f"/ws/reclamos/{self.categoria.id}/?token={operator_token}"
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        msg = await communicator.receive_json_from()
        self.assertEqual(msg["event"], "presence_update")
        self.assertEqual(msg["user"], "operador_ws")
        self.assertEqual(msg["status"], "online")

        await communicator.disconnect()

    def test_crear_reclamo_triggers_notification_on_commit(self):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)("reclamos_publicos", "test_channel")

        reclamo = ReclamoService.crear_reclamo(
            usuario=self.neighbor,
            titulo="Luminaria apagada",
            descripcion="La farola de la esquina no enciende desde ayer.",
            categoria_id=self.categoria.id
        )

        event = async_to_sync(channel_layer.receive)("test_channel")
        self.assertEqual(event["type"], "reclamo_notification")
        self.assertEqual(event["payload"]["evento"], "NUEVO_RECLAMO")
        self.assertEqual(event["payload"]["id"], reclamo.id)