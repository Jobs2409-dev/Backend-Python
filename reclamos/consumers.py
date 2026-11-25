# backend_python/reclamos/consumers.py
import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Categoria
from .presence import (
    register_category_presence,
    unregister_category_presence,
)


@database_sync_to_async
def categoria_existe(categoria_id: int) -> bool:
    return Categoria.objects.filter(id=categoria_id).exists()


class ReclamoNotificationConsumer(AsyncWebsocketConsumer):
    """
    CLASE 9 & 10: Consumer asincrónico para notificaciones de reclamos en tiempo real,
    control de acceso en canales por categoría y presencia online/offline.
    """
    async def connect(self):
        self.categoria_id = self.scope["url_route"]["kwargs"].get("categoria_id")
        self.user = self.scope.get("user")
        self.joined = False
        self.presence_registered = False

        if self.categoria_id:
            # Canal operativo por categoría: requiere usuario autenticado con rol OPERADOR o ADMIN
            if not self.user or not self.user.is_authenticated:
                await self.close()
                return

            self.role_name = self.user.rol.nombre if self.user.rol else None
            if self.role_name not in ["OPERADOR", "ADMIN"]:
                await self.close()
                return

            existe = await categoria_existe(self.categoria_id)
            if not existe:
                await self.close()
                return

            self.group_name = f"categoria_{self.categoria_id}"
        else:
            # Canal público: lectura abierta para dashboard ciudadano
            self.group_name = "reclamos_publicos"

        # Se une al grupo en Redis
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self.joined = True

        # Emite presencia online si el usuario está autenticado en un canal de categoría
        if self.categoria_id and self.user and self.user.is_authenticated:
            existing_users, first_connection = await register_category_presence(
                self.categoria_id,
                self.channel_name,
                self.user.pk,
                self.user.username,
                self.role_name,
            )
            self.presence_registered = True
            for existing_user in existing_users:
                await self.send(
                    text_data=json.dumps(
                        {
                            "event": "presence_update",
                            **existing_user,
                            "status": "online",
                        }
                    )
                )

            if first_connection:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "presence_update",
                        "payload": {
                            "event": "presence_update",
                            "user": self.user.username,
                            "rol": self.role_name,
                            "status": "online",
                        },
                    },
                )

    async def disconnect(self, close_code):
        # Si la conexión fue rechazada en connect(), nunca entró al grupo
        if not getattr(self, "joined", False):
            return

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

        if (
            self.categoria_id
            and self.user
            and self.user.is_authenticated
            and self.presence_registered
        ):
            last_connection = await unregister_category_presence(
                self.categoria_id,
                self.channel_name,
                self.user.pk,
            )
            if not last_connection:
                return

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "presence_update",
                    "payload": {
                        "event": "presence_update",
                        "user": self.user.username,
                        "rol": self.role_name,
                        "status": "offline",
                    },
                },
            )

    async def receive(self, text_data):
        # Maneja mensajes enviados desde el cliente (Modo Echo para pruebas)
        data = json.loads(text_data)
        await self.send(text_data=json.dumps({"echo": data}))

    async def reclamo_notification(self, event):
        # Retransmite notificaciones de negocio a los clientes del grupo (Clase 10)
        await self.send(text_data=json.dumps(event["payload"]))

    async def presence_update(self, event):
        # Retransmite cambios de presencia (online / offline) al grupo (Clase 10)
        await self.send(text_data=json.dumps(event["payload"]))