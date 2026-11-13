# backend_python/reclamos/ws_auth.py
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


# ==============================================================================
# CLASE 10: Autenticación JWT en Handshake WebSocket
# Concepto: Los navegadores no permiten enviar el header Authorization en una
# conexión WebSocket nativa, por lo que se extrae ?token=<access> de la URL,
# se valida con SimpleJWT y se inyecta el usuario en scope["user"].
# ==============================================================================

@database_sync_to_async
def get_user_from_token(token: str):
    User = get_user_model()
    try:
        access = AccessToken(token)
        return User.objects.select_related('rol').get(id=access["user_id"])
    except (TokenError, KeyError, User.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Lee ?token=<access> de la URL del WebSocket y completa scope['user']."""

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [None])[0]
        if token:
            scope["user"] = await get_user_from_token(token)
        return await super().__call__(scope, receive, send)