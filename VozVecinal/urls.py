# backend_python/VozVecinal/urls.py
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt
from reclamos.views import SocialLoginJWTView
from reclamos.graphql_views import JWTGraphQLView


def health_check(request):
    return JsonResponse({"status": "ok", "service": "VozVecinal API"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/', include('reclamos.urls')),
    
    # Rutas oficiales de django-allauth (Clase 7)
    path('accounts/', include('allauth.urls')),
    path('api/auth/social/jwt/', SocialLoginJWTView.as_view(), name='social_jwt'),
    
    # Endpoint GraphQL con soporte JWT y explorador GraphiQL (Clase 11)
    path('graphql/', csrf_exempt(JWTGraphQLView.as_view(graphiql=True)), name='graphql'),
]
