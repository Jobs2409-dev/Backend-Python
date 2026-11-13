# backend_python/reclamos/schema.py
import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import AreaDependencia, Categoria, Estado, Reclamo, RegistroHistorial
from .repositories import ReclamoRepository
from .serializers import ReclamoCreateUpdateSerializer, CambiarEstadoReclamoSerializer
from .services import ReclamoService

User = get_user_model()


# ==============================================================================
# CLASE 11: Definición de Tipos GraphQL (DjangoObjectType)
# Concepto: Exposición explícita de campos del dominio evitando filtrar datos
# sensibles (como contraseña, DNI, teléfono o email en consultas públicas).
# ==============================================================================

class UsuarioPublicoType(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username")


class AreaDependenciaType(DjangoObjectType):
    class Meta:
        model = AreaDependencia
        fields = ("id", "nombre", "descripcion", "categorias")


class CategoriaType(DjangoObjectType):
    class Meta:
        model = Categoria
        fields = ("id", "nombre", "descripcion", "area", "reclamos")


class EstadoType(DjangoObjectType):
    class Meta:
        model = Estado
        fields = ("id", "nombre")


class RegistroHistorialType(DjangoObjectType):
    usuario_operador = graphene.Field(UsuarioPublicoType)

    class Meta:
        model = RegistroHistorial
        fields = ("id", "estado", "observacion", "fecha", "usuario_operador")


class ReclamoType(DjangoObjectType):
    usuario = graphene.Field(UsuarioPublicoType)

    class Meta:
        model = Reclamo
        fields = (
            "id",
            "titulo",
            "descripcion",
            "fecha_creacion",
            "usuario",
            "categoria",
            "estado_actual",
            "registros",
        )


# ==============================================================================
# CLASE 11: Queries y Reglas de Visibilidad por Rol / Propietario
# Concepto: Reutilización de la misma lógica de acceso que ReclamoViewSet.
# ==============================================================================

def reclamos_visibles_para(user):
    """
    Aplica la misma regla que ReclamoViewSet.get_queryset:
    - Anónimo: ninguno.
    - OPERADOR / ADMIN: todos los reclamos optimizados.
    - VECINO: solo sus propios reclamos.
    """
    if not user or not user.is_authenticated:
        return ReclamoRepository.get_all_optimized().none()

    if user.rol and user.rol.nombre in ["OPERADOR", "ADMIN"]:
        return ReclamoRepository.get_all_optimized()

    return ReclamoRepository.get_by_user_optimized(user)


class Query(graphene.ObjectType):
    todas_las_areas = graphene.List(AreaDependenciaType)
    todas_las_categorias = graphene.List(CategoriaType)
    todos_los_estados = graphene.List(EstadoType)

    mis_reclamos = graphene.List(ReclamoType)
    reclamo = graphene.Field(ReclamoType, id=graphene.ID(required=True))
    reclamos_por_estado = graphene.List(ReclamoType, estado=graphene.String(required=True))
    reclamos_publicos = graphene.List(ReclamoType)

    def resolve_todas_las_areas(root, info):
        return AreaDependencia.objects.prefetch_related("categorias").all()

    def resolve_todas_las_categorias(root, info):
        return Categoria.objects.select_related("area").all()

    def resolve_todos_los_estados(root, info):
        return Estado.objects.all()

    def resolve_mis_reclamos(root, info):
        return reclamos_visibles_para(info.context.user).prefetch_related(
            "registros__estado", "registros__usuario_operador"
        )

    def resolve_reclamo(root, info, id):
        return (
            reclamos_visibles_para(info.context.user)
            .prefetch_related("registros__estado", "registros__usuario_operador")
            .filter(pk=id)
            .first()
        )

    def resolve_reclamos_por_estado(root, info, status=None, **kwargs):
        estado = kwargs.get("estado") or status
        return (
            reclamos_visibles_para(info.context.user)
            .filter(estado_actual__nombre__iexact=estado)
            .prefetch_related("registros__estado", "registros__usuario_operador")
        )

    def resolve_reclamos_publicos(root, info):
        return ReclamoRepository.get_all_optimized().prefetch_related(
            "registros__estado", "registros__usuario_operador"
        )[:50]
        
# ==============================================================================
# CLASE 11: Mutations (Escritura de Datos)
# Concepto: Reutilización de Serializers (validación + sanitización XSS con nh3)
# y de ReclamoService (transacciones ACID, historial y eventos en Redis).
# ==============================================================================

def _obtener_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0]
    return request.META.get("REMOTE_ADDR")


class CrearReclamo(graphene.Mutation):
    class Arguments:
        titulo = graphene.String(required=True)
        descripcion = graphene.String(required=True)
        categoria_id = graphene.ID(required=True)

    reclamo = graphene.Field(ReclamoType)
    ok = graphene.Boolean()

    def mutate(root, info, titulo, descripcion, categoria_id):
        user = info.context.user
        if not user or not user.is_authenticated:
            raise GraphQLError("Autenticación requerida para crear un reclamo.")

        serializer = ReclamoCreateUpdateSerializer(
            data={
                "titulo": titulo,
                "descripcion": descripcion,
                "categoria": categoria_id,
            }
        )
        if not serializer.is_valid():
            errores = {
                campo: [str(e) for e in lista]
                for campo, lista in serializer.errors.items()
            }
            raise GraphQLError(f"Datos inválidos: {errores}")

        try:
            reclamo = ReclamoService.crear_reclamo(
                usuario=user,
                titulo=serializer.validated_data["titulo"],
                descripcion=serializer.validated_data["descripcion"],
                categoria_id=serializer.validated_data["categoria"].id,
                ip_address=_obtener_ip(info.context),
            )
        except ValidationError as e:
            raise GraphQLError(e.message)

        return CrearReclamo(reclamo=reclamo, ok=True)


class CambiarEstadoReclamo(graphene.Mutation):
    class Arguments:
        reclamo_id = graphene.ID(required=True)
        nuevo_estado_id = graphene.ID(required=True)
        observacion = graphene.String(required=True)

    reclamo = graphene.Field(ReclamoType)
    ok = graphene.Boolean()

    def mutate(root, info, reclamo_id, nuevo_estado_id, observacion):
        user = info.context.user
        if not user or not user.is_authenticated:
            raise GraphQLError("Autenticación requerida.")

        rol_nombre = user.rol.nombre if user.rol else None
        if rol_nombre not in ["OPERADOR", "ADMIN"]:
            raise GraphQLError("Solo un Operador o Administrador puede cambiar el estado de un reclamo.")

        serializer = CambiarEstadoReclamoSerializer(
            data={
                "nuevo_estado_id": nuevo_estado_id,
                "observacion": observacion,
            }
        )
        if not serializer.is_valid():
            errores = {
                campo: [str(e) for e in lista]
                for campo, lista in serializer.errors.items()
            }
            raise GraphQLError(f"Datos inválidos: {errores}")

        try:
            reclamo_actualizado = ReclamoService.cambiar_estado(
                reclamo_id=int(reclamo_id),
                nuevo_estado_id=serializer.validated_data["nuevo_estado_id"],
                operador=user,
                observacion=serializer.validated_data["observacion"],
                ip_address=_obtener_ip(info.context),
            )
        except ValidationError as e:
            raise GraphQLError(e.message)

        return CambiarEstadoReclamo(reclamo=reclamo_actualizado, ok=True)


class Mutation(graphene.ObjectType):
    crear_reclamo = CrearReclamo.Field()
    cambiar_estado_reclamo = CambiarEstadoReclamo.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)