from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.permissions import EsCualquierUsuario
from apps.seguridad.views import registrar_bitacora

from .serializers import CambiarPasswordPerfilSerializer, PerfilUsuarioSerializer


# CRUD reducido de perfil:
# GET muestra los datos del usuario autenticado.
# PUT actualiza datos personales permitidos.
@extend_schema(tags=["Perfil de Usuario"])
class PerfilUsuarioView(APIView):
    permission_classes = [EsCualquierUsuario]

    @extend_schema(
        summary="Ver perfil del usuario autenticado",
        responses={200: PerfilUsuarioSerializer}
    )
    def get(self, request):
        # request.usuario_actual viene del middleware/autenticacion JWT personalizada.
        usuario = getattr(request, 'usuario_actual', request.user)
        return Response(PerfilUsuarioSerializer(usuario).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar perfil del usuario autenticado",
        description="Permite actualizar datos personales. No permite cambiar codigo, rol ni permisos.",
        request=PerfilUsuarioSerializer,
        responses={
            200: OpenApiResponse(description="Perfil actualizado."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Actualizar perfil",
                value={
                    "nombre": "Juan Carlos",
                    "apellido": "Perez",
                    "telefono": "78945612",
                    "correo": "juan.nuevo@gmail.com",
                },
                request_only=True,
            )
        ]
    )
    def put(self, request):
        # partial=True permite actualizar solo los campos enviados desde el frontend.
        usuario = getattr(request, 'usuario_actual', request.user)
        serializer = PerfilUsuarioSerializer(usuario, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_PERFIL', f'Perfil actualizado: {usuario.codigo}.', usuario)
            return Response(
                {'mensaje': 'Perfil actualizado correctamente.', 'perfil': PerfilUsuarioSerializer(usuario).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Endpoint especifico para cambio de contrasena dentro del perfil.
# Es independiente del flujo "olvide mi contrasena", que usa codigo por correo.
@extend_schema(tags=["Perfil de Usuario"])
class CambiarPasswordPerfilView(APIView):
    permission_classes = [EsCualquierUsuario]

    @extend_schema(
        summary="Cambiar contraseña del perfil",
        description="Cambia la contraseña del usuario autenticado y la guarda encriptada en la base de datos.",
        request=CambiarPasswordPerfilSerializer,
        responses={
            200: OpenApiResponse(description="Contraseña actualizada."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Cambiar contraseña",
                value={
                    "password_actual": "actual123",
                    "nueva_password": "nueva123",
                    "confirmar_password": "nueva123",
                },
                request_only=True,
            )
        ]
    )
    def put(self, request):
        # Valida contrasena actual y guarda la nueva contrasena hasheada.
        usuario = getattr(request, 'usuario_actual', request.user)
        serializer = CambiarPasswordPerfilSerializer(
            data=request.data,
            context={'usuario': usuario}
        )
        if serializer.is_valid():
            serializer.save()
            registrar_bitacora(request, 'CAMBIAR_PASSWORD_PERFIL', f'Contraseña actualizada desde perfil: {usuario.codigo}.', usuario)
            return Response({'mensaje': 'Contraseña actualizada correctamente.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
