from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from .models import Rol, Usuario
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    RolSerializer,
    UsuarioListSerializer,
    UsuarioCrearSerializer,
    UsuarioActualizarSerializer,
    BarberoCrearSerializer,
    BarberoSerializer,
)
from .permissions import EsAdmin, EsAdminOConfiguracionInicial, EsCualquierUsuario
from .authentication import generar_tokens


# ─────────────────────────────────────────────────────────────────────────────
# CU1 — Iniciar Sesión  (A1, A2, A3)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["CU1 - Autenticación"],
    summary="Iniciar sesión",
    description="Autentica a un usuario por correo electronico y password; el codigo es el carnet de identidad.",
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(
            description="Login exitoso.",
            response={
                "type": "object",
                "properties": {
                    "access":   {"type": "string", "example": "eyJhbGciOiJIUzI1..."},
                    "refresh":  {"type": "string", "example": "eyJhbGciOiJIUzI1..."},
                    "usuario": {
                        "type": "object",
                        "properties": {
                            "codigo":   {"type": "string", "example": "ADMIN001"},
                            "nombre":   {"type": "string", "example": "Administrador"},
                            "apellido": {"type": "string", "example": "Sistema"},
                            "correo":   {"type": "string", "example": "admin@blessedbarber.com"},
                            "rol":      {"type": "string", "example": "Administrador"},
                        }
                    }
                }
            }
        ),
        400: OpenApiResponse(description="Credenciales incorrectas."),
    },
    examples=[
        OpenApiExample("Administrador", value={"correo": "admin@blessedbarber.com", "password": "admin123"}, request_only=True),
        OpenApiExample("Barbero",       value={"correo": "barbero@blessedbarber.com", "password": "barb123"}, request_only=True),
        OpenApiExample("Cliente",       value={"correo": "cliente@gmail.com", "password": "clie123"}, request_only=True),
    ]
)
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        usuario = serializer.validated_data['usuario']
        tokens = generar_tokens(usuario)
        return Response(tokens, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# CU2 — Cerrar Sesión  (A1, A2, A3)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["CU2 - Autenticación"],
    summary="Cerrar sesión",
    description="Invalida el refresh token. Requiere Bearer token en el header Authorization.",
    request=LogoutSerializer,
    responses={
        200: OpenApiResponse(description="Sesión cerrada correctamente."),
        400: OpenApiResponse(description="Token inválido o no enviado."),
    },
    examples=[
        OpenApiExample("Logout", value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}, request_only=True)
    ]
)
class LogoutView(APIView):
    permission_classes = [EsCualquierUsuario]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        refresh_token = serializer.validated_data['refresh']
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'mensaje': 'Sesión cerrada correctamente.'}, status=status.HTTP_200_OK)
        except TokenError:
            return Response({'error': 'Token inválido o ya expirado.'}, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# CU3 — Gestionar Usuarios  (solo A1)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["CU3 - Gestionar Usuarios"])
class UsuarioListCreateView(APIView):
    permission_classes = [EsAdminOConfiguracionInicial]

    @extend_schema(
        summary="Listar todos los usuarios",
        description="Solo Administrador puede listar usuarios.",
        responses={200: UsuarioListSerializer(many=True), 403: OpenApiResponse(description="Sin permiso.")}
    )
    def get(self, request):
        usuarios = Usuario.objects.select_related('id_rol').all()
        serializer = UsuarioListSerializer(usuarios, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear un nuevo usuario",
        description="Solo Administrador puede crear usuarios.",
        request=BarberoCrearSerializer,
        responses={
            201: OpenApiResponse(description="Usuario creado correctamente."),
            400: OpenApiResponse(description="Datos inválidos."),
        },
        examples=[
            OpenApiExample(
                "Crear cliente",
                value={"codigo": "CLIE001", "nombre": "Juan", "apellido": "Pérez",
                       "telefono": "76543210", "correo": "juan@gmail.com",
                       "password": "pass123", "id_rol": 3},
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = UsuarioCrearSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'mensaje': 'Usuario creado correctamente.', 'usuario': serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU3 - Gestionar Usuarios"])
class UsuarioDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_usuario(self, codigo):
        try:
            return Usuario.objects.select_related('id_rol').get(codigo=codigo)
        except Usuario.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de un usuario",
        responses={200: UsuarioListSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, codigo):
        usuario = self._get_usuario(codigo)
        if not usuario:
            return Response({'error': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(UsuarioListSerializer(usuario).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar un usuario",
        request=UsuarioActualizarSerializer,
        responses={
            200: OpenApiResponse(description="Actualizado correctamente."),
            400: OpenApiResponse(description="Datos inválidos."),
            404: OpenApiResponse(description="No encontrado."),
        },
        examples=[
            OpenApiExample("Actualizar", value={"telefono": "71234567", "correo": "nuevo@gmail.com"}, request_only=True)
        ]
    )
    def put(self, request, codigo):
        usuario = self._get_usuario(codigo)
        if not usuario:
            return Response({'error': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = UsuarioActualizarSerializer(usuario, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'mensaje': 'Usuario actualizado correctamente.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Eliminar un usuario",
        responses={
            200: OpenApiResponse(description="Eliminado correctamente."),
            400: OpenApiResponse(description="No puedes eliminarte a ti mismo."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def delete(self, request, codigo):
        usuario = self._get_usuario(codigo)
        if not usuario:
            return Response({'error': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        usuario_actual = getattr(request, 'usuario_actual', None)
        if usuario_actual and usuario_actual.codigo == codigo:
            return Response({'error': 'No puedes eliminar tu propia cuenta.'}, status=status.HTTP_400_BAD_REQUEST)
        usuario.delete()
        return Response({'mensaje': 'Usuario eliminado correctamente.'}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# CU4 — Gestionar Roles  (solo A1)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["CU4 - Gestionar Roles"])
class RolListCreateView(APIView):
    permission_classes = [EsAdminOConfiguracionInicial]

    @extend_schema(
        summary="Listar todos los roles",
        responses={200: RolSerializer(many=True)}
    )
    def get(self, request):
        roles = Rol.objects.all()
        return Response(RolSerializer(roles, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear un nuevo rol",
        request=RolSerializer,
        responses={
            201: OpenApiResponse(description="Rol creado."),
            400: OpenApiResponse(description="Datos inválidos."),
        },
        examples=[OpenApiExample("Crear rol", value={"nombre": "Cajero"}, request_only=True)]
    )
    def post(self, request):
        serializer = RolSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'mensaje': 'Rol creado correctamente.', 'rol': serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU4 - Gestionar Roles"])
class RolDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_rol(self, id):
        try:
            return Rol.objects.get(pk=id)
        except Rol.DoesNotExist:
            return None

    @extend_schema(
        summary="Actualizar un rol",
        request=RolSerializer,
        responses={
            200: OpenApiResponse(description="Rol actualizado."),
            404: OpenApiResponse(description="No encontrado."),
        },
        examples=[OpenApiExample("Renombrar", value={"nombre": "Supervisor"}, request_only=True)]
    )
    def put(self, request, id):
        rol = self._get_rol(id)
        if not rol:
            return Response({'error': 'Rol no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = RolSerializer(rol, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'mensaje': 'Rol actualizado correctamente.', 'rol': serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Eliminar un rol",
        responses={
            200: OpenApiResponse(description="Rol eliminado."),
            400: OpenApiResponse(description="Tiene usuarios asignados."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def delete(self, request, id):
        rol = self._get_rol(id)
        if not rol:
            return Response({'error': 'Rol no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        if rol.usuarios.exists():
            return Response({'error': 'No se puede eliminar el rol porque tiene usuarios asignados.'}, status=status.HTTP_400_BAD_REQUEST)
        rol.delete()
        return Response({'mensaje': 'Rol eliminado correctamente.'}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# CU5 — Gestionar Barberos  (solo A1)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["CU5 - Gestionar Barberos"])
class BarberoListCreateView(APIView):
    permission_classes = [EsAdmin]

    def _get_rol_barbero(self):
        try:
            return Rol.objects.get(nombre__iexact='barbero')
        except Rol.DoesNotExist:
            return None

    @extend_schema(
        summary="Listar todos los barberos",
        responses={
            200: BarberoSerializer(many=True),
            404: OpenApiResponse(description="Rol Barbero no existe."),
        }
    )
    def get(self, request):
        rol_barbero = self._get_rol_barbero()
        if not rol_barbero:
            return Response({'error': 'El rol "Barbero" no existe en el sistema.'}, status=status.HTTP_404_NOT_FOUND)
        barberos = Usuario.objects.select_related('id_rol').filter(id_rol=rol_barbero)
        return Response(BarberoSerializer(barberos, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Registrar un nuevo barbero",
        description="El id_rol se asigna automáticamente como Barbero. No hace falta enviarlo.",
        request=BarberoCrearSerializer,
        responses={
            201: OpenApiResponse(description="Barbero registrado."),
            400: OpenApiResponse(description="Datos inválidos."),
            404: OpenApiResponse(description="Rol Barbero no existe."),
        },
        examples=[
            OpenApiExample(
                "Registrar barbero",
                value={"codigo": "BARB001", "nombre": "Carlos", "apellido": "Mamani",
                       "telefono": "78901234", "correo": "carlos@blessedbarber.com", "password": "barb123"},
                request_only=True,
            )
        ]
    )
    def post(self, request):
        rol_barbero = self._get_rol_barbero()
        if not rol_barbero:
            return Response({'error': 'El rol "Barbero" no existe. Créalo primero.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BarberoCrearSerializer(data=request.data)
        if serializer.is_valid():
            barbero = serializer.save(id_rol=rol_barbero)
            return Response(
                {'mensaje': 'Barbero registrado correctamente.', 'barbero': BarberoSerializer(barbero).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU5 - Gestionar Barberos"])
class BarberoDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_barbero(self, codigo):
        try:
            return Usuario.objects.select_related('id_rol').get(codigo=codigo, id_rol__nombre__iexact='barbero')
        except Usuario.DoesNotExist:
            return None

    @extend_schema(
        summary="Actualizar un barbero",
        request=UsuarioActualizarSerializer,
        responses={
            200: OpenApiResponse(description="Barbero actualizado."),
            400: OpenApiResponse(description="Datos inválidos."),
            404: OpenApiResponse(description="Barbero no encontrado."),
        },
        examples=[
            OpenApiExample("Actualizar barbero", value={"telefono": "79876543", "correo": "nuevo@barbero.com"}, request_only=True)
        ]
    )
    def put(self, request, codigo):
        barbero = self._get_barbero(codigo)
        if not barbero:
            return Response({'error': 'Barbero no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = UsuarioActualizarSerializer(barbero, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'mensaje': 'Barbero actualizado correctamente.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Eliminar un barbero",
        responses={
            200: OpenApiResponse(description="Barbero eliminado."),
            404: OpenApiResponse(description="Barbero no encontrado."),
        }
    )
    def delete(self, request, codigo):
        barbero = self._get_barbero(codigo)
        if not barbero:
            return Response({'error': 'Barbero no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        barbero.delete()
        return Response({'mensaje': 'Barbero eliminado correctamente.'}, status=status.HTTP_200_OK)
