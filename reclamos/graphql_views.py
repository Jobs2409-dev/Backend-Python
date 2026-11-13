# backend_python/reclamos/graphql_views.py
from graphene_django.views import GraphQLView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


# ==============================================================================
# CLASE 11: Vista GraphQL Autenticada con JWT
# Concepto: GraphQLView es una vista estándar de Django (no de DRF), por lo que
# no procesa el header Authorization por defecto. Sobrescribimos dispatch()
# para reutilizar JWTAuthentication de SimpleJWT antes de ejecutar el esquema.
# ==============================================================================
class JWTGraphQLView(GraphQLView):

    def dispatch(self, request, *args, **kwargs):
        try:
            result = JWTAuthentication().authenticate(request)
        except AuthenticationFailed:
            result = None

        if result is not None:
            request.user, _ = result

        return super().dispatch(request, *args, **kwargs)