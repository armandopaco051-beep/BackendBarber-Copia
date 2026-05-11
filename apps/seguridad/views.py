from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
import secrets

from .models import AsistenciaBarbero, Bitacora, BloqueoHorario, HorarioLaboral, Rol, Usuario
from .serializers import (
    AsistenciaBarberoSerializer,
    BitacoraSerializer,
    BloqueoHorarioSerializer,
    HorarioLaboralSerializer,
    LoginSerializer,
    LogoutSerializer,
    SolicitarRecuperacionSerializer,
    ValidarCodigoRecuperacionSerializer,
    RestablecerPasswordSerializer,
    RolSerializer,
    UsuarioListSerializer,
    UsuarioCrearSerializer,
    UsuarioActualizarSerializer,
    ClienteRegistroSerializer,
    BarberoCrearSerializer,
    BarberoSerializer,
)
from .permissions import EsAdmin, EsAdminOConfiguracionInicial, EsAdminOLecturaAutenticada, EsCualquierUsuario
from .authentication import generar_tokens


def obtener_ip_cliente(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def registrar_bitacora(request, accion, descripcion='', usuario=None):
    try:
        usuario = usuario or getattr(request, 'usuario_actual', None)
        Bitacora.objects.create(
            usuario=usuario,
            accion=accion,
            descripcion=descripcion,
            metodo=request.method,
            ruta=request.path,
            ip=obtener_ip_cliente(request),
        )
    except Exception:
        pass


def generar_codigo_recuperacion():
    return f"{secrets.randbelow(1000000):06d}"


def validar_codigo_usuario(usuario, codigo):
    if not usuario.codigo_recuperacion or not usuario.codigo_recuperacion_expira:
        return False, "No hay un código de recuperación activo."
    if usuario.codigo_recuperacion_expira < timezone.now():
        return False, "El código de recuperación expiró. Solicite uno nuevo."
    if not check_password(codigo, usuario.codigo_recuperacion):
        return False, "Código de recuperación inválido."
    return True, None


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
            correo = request.data.get('correo', '')
            usuario = Usuario.objects.filter(correo__iexact=correo).first()
            registrar_bitacora(request, 'LOGIN_FALLIDO', f'Intento fallido de login para correo {correo}.', usuario)
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        usuario = serializer.validated_data['usuario']
        tokens = generar_tokens(usuario)
        registrar_bitacora(request, 'LOGIN', 'Inicio de sesión exitoso.', usuario)
        return Response(tokens, status=status.HTTP_200_OK)


@extend_schema(
    tags=["CU1 - Autenticación"],
    summary="Registro público de cliente",
    description="Registra un cliente sin token. El backend asigna automáticamente el rol Cliente con id_rol=3.",
    request=ClienteRegistroSerializer,
    responses={
        201: OpenApiResponse(description="Cliente registrado correctamente."),
        400: OpenApiResponse(description="Datos inválidos."),
        404: OpenApiResponse(description="Rol Cliente no configurado."),
    },
    examples=[
        OpenApiExample(
            "Registrar cliente",
            value={
                "codigo": "12345678",
                "nombre": "Juan",
                "apellido": "Perez",
                "telefono": "76543210",
                "correo": "juan@gmail.com",
                "password": "cliente123",
            },
            request_only=True,
        )
    ]
)
class RegistroClienteView(APIView):
    permission_classes = [AllowAny]

    def _get_rol_cliente(self):
        try:
            rol = Rol.objects.get(id=3)
        except Rol.DoesNotExist:
            return None
        if rol.nombre.lower() != 'cliente':
            return None
        return rol

    def post(self, request):
        rol_cliente = self._get_rol_cliente()
        if not rol_cliente:
            return Response(
                {'error': 'El rol Cliente debe existir con id=3 antes de registrar clientes.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ClienteRegistroSerializer(data=request.data)
        if serializer.is_valid():
            cliente = serializer.save(id_rol=rol_cliente)
            registrar_bitacora(request, 'REGISTRO_CLIENTE', f'Cliente registrado: {cliente.codigo}.', cliente)
            return Response(
                {'mensaje': 'Cliente registrado correctamente.', 'cliente': UsuarioListSerializer(cliente).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            registrar_bitacora(request, 'LOGOUT', 'Cierre de sesión exitoso.')
            return Response({'mensaje': 'Sesión cerrada correctamente.'}, status=status.HTTP_200_OK)
        except TokenError:
            registrar_bitacora(request, 'LOGOUT_FALLIDO', 'Intento de cierre de sesión con token inválido.')
            return Response({'error': 'Token inválido o ya expirado.'}, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# CU3 — Gestionar Usuarios  (solo A1)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["CU2 - Autenticación"],
    summary="Solicitar recuperación de contraseña",
    description="Envía un código temporal al correo del usuario para restablecer la contraseña.",
    request=SolicitarRecuperacionSerializer,
    responses={
        200: OpenApiResponse(description="Si el correo existe, se enviará un código temporal."),
        400: OpenApiResponse(description="Datos inválidos."),
        500: OpenApiResponse(description="No se pudo enviar el correo."),
    },
    examples=[OpenApiExample("Solicitar código", value={"correo": "admin@gmail.com"}, request_only=True)]
)
class SolicitarRecuperacionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SolicitarRecuperacionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        correo = serializer.validated_data['correo'].lower()
        usuario = Usuario.objects.filter(correo__iexact=correo).first()
        respuesta = {'mensaje': 'Si el correo existe, se enviará un código temporal.'}

        if not usuario:
            registrar_bitacora(request, 'SOLICITAR_RECUPERACION', f'Solicitud de recuperación para correo no registrado: {correo}.')
            return Response(respuesta, status=status.HTTP_200_OK)

        codigo = generar_codigo_recuperacion()
        usuario.codigo_recuperacion = make_password(codigo)
        usuario.codigo_recuperacion_expira = timezone.now() + timedelta(minutes=10)
        usuario.save(update_fields=['codigo_recuperacion', 'codigo_recuperacion_expira'])

        try:
            send_mail(
                subject='Código de recuperación - Blessed Barber Club',
                message=(
                    f'Hola {usuario.nombre},\n\n'
                    f'Tu código de recuperación es: {codigo}\n\n'
                    'Este código vence en 10 minutos.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[usuario.correo],
                fail_silently=False,
            )
        except Exception:
            registrar_bitacora(request, 'SOLICITAR_RECUPERACION_FALLIDA', f'No se pudo enviar código de recuperación a {usuario.correo}.', usuario)
            return Response({'error': 'No se pudo enviar el correo de recuperación.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        registrar_bitacora(request, 'SOLICITAR_RECUPERACION', f'Código de recuperación enviado a {usuario.correo}.', usuario)
        return Response(respuesta, status=status.HTTP_200_OK)


@extend_schema(
    tags=["CU2 - Autenticación"],
    summary="Validar código de recuperación",
    description="Valida el código temporal antes de mostrar el formulario de nueva contraseña.",
    request=ValidarCodigoRecuperacionSerializer,
    responses={
        200: OpenApiResponse(description="Código válido."),
        400: OpenApiResponse(description="Código inválido o expirado."),
    },
    examples=[OpenApiExample("Validar código", value={"correo": "admin@gmail.com", "codigo": "123456"}, request_only=True)]
)
class ValidarCodigoRecuperacionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ValidarCodigoRecuperacionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = Usuario.objects.filter(correo__iexact=serializer.validated_data['correo']).first()
        if not usuario:
            registrar_bitacora(request, 'VALIDAR_CODIGO_FALLIDO', 'Validación de código para correo no registrado.')
            return Response({'error': 'Código de recuperación inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        es_valido, error = validar_codigo_usuario(usuario, serializer.validated_data['codigo'])
        if not es_valido:
            registrar_bitacora(request, 'VALIDAR_CODIGO_FALLIDO', error, usuario)
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        registrar_bitacora(request, 'VALIDAR_CODIGO', 'Código de recuperación validado correctamente.', usuario)
        return Response({'mensaje': 'Código válido. Puede restablecer la contraseña.'}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["CU2 - Autenticación"],
    summary="Restablecer contraseña",
    description="Cambia la contraseña luego de validar el código temporal enviado al correo.",
    request=RestablecerPasswordSerializer,
    responses={
        200: OpenApiResponse(description="Contraseña actualizada correctamente."),
        400: OpenApiResponse(description="Datos inválidos."),
    },
    examples=[
        OpenApiExample(
            "Restablecer contraseña",
            value={
                "correo": "admin@gmail.com",
                "codigo": "123456",
                "nueva_password": "nuevo123",
                "confirmar_password": "nuevo123",
            },
            request_only=True,
        )
    ]
)
class RestablecerPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RestablecerPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = Usuario.objects.filter(correo__iexact=serializer.validated_data['correo']).first()
        if not usuario:
            registrar_bitacora(request, 'RESTABLECER_PASSWORD_FALLIDO', 'Restablecimiento para correo no registrado.')
            return Response({'error': 'Código de recuperación inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        es_valido, error = validar_codigo_usuario(usuario, serializer.validated_data['codigo'])
        if not es_valido:
            registrar_bitacora(request, 'RESTABLECER_PASSWORD_FALLIDO', error, usuario)
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        usuario.password = make_password(serializer.validated_data['nueva_password'])
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.codigo_recuperacion = None
        usuario.codigo_recuperacion_expira = None
        usuario.save(update_fields=[
            'password',
            'intentos_fallidos',
            'bloqueado_hasta',
            'codigo_recuperacion',
            'codigo_recuperacion_expira',
        ])

        registrar_bitacora(request, 'RESTABLECER_PASSWORD', 'Contraseña restablecida correctamente.', usuario)
        return Response({'mensaje': 'Contraseña actualizada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU6 - Bitácora"])
class BitacoraListView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar bitácora",
        description="Solo Administrador puede consultar las últimas acciones registradas.",
        responses={200: BitacoraSerializer(many=True)}
    )
    def get(self, request):
        registrar_bitacora(request, 'CONSULTAR_BITACORA', 'Consulta de bitácora del sistema.')
        registros = Bitacora.objects.select_related('usuario', 'usuario__id_rol').all()[:200]
        return Response(BitacoraSerializer(registros, many=True).data, status=status.HTTP_200_OK)


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
        request=UsuarioCrearSerializer,
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
            usuario = serializer.save()
            registrar_bitacora(request, 'CREAR_USUARIO', f'Usuario creado: {usuario.codigo}.')
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
            registrar_bitacora(request, 'ACTUALIZAR_USUARIO', f'Usuario actualizado: {usuario.codigo}.')
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
        codigo_usuario = usuario.codigo
        usuario.delete()
        registrar_bitacora(request, 'ELIMINAR_USUARIO', f'Usuario eliminado: {codigo_usuario}.')
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
            rol = serializer.save()
            registrar_bitacora(request, 'CREAR_ROL', f'Rol creado: {rol.nombre}.')
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
            nombre_anterior = rol.nombre
            serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_ROL', f'Rol actualizado: {nombre_anterior} -> {rol.nombre}.')
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
        nombre_rol = rol.nombre
        rol.delete()
        registrar_bitacora(request, 'ELIMINAR_ROL', f'Rol eliminado: {nombre_rol}.')
        return Response({'mensaje': 'Rol eliminado correctamente.'}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# CU5 — Gestionar Barberos  (solo A1)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["CU5 - Gestionar Barberos"])
class BarberoListCreateView(APIView):
    permission_classes = [EsAdminOLecturaAutenticada]

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
                       "telefono": "78901234", "correo": "carlos@blessedbarber.com",
                       "especialidad": "Corte clásico", "password": "barb123"},
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
            registrar_bitacora(request, 'CREAR_BARBERO', f'Barbero registrado: {barbero.codigo}.')
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
            registrar_bitacora(request, 'ACTUALIZAR_BARBERO', f'Barbero actualizado: {barbero.codigo}.')
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
        codigo_barbero = barbero.codigo
        barbero.delete()
        registrar_bitacora(request, 'ELIMINAR_BARBERO', f'Barbero eliminado: {codigo_barbero}.')
        return Response({'mensaje': 'Barbero eliminado correctamente.'}, status=status.HTTP_200_OK)


# CU8 - Gestionar horarios laborales

@extend_schema(tags=["CU8 - Gestionar Horarios Laborales"])
class HorarioLaboralListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar horarios laborales",
        description="Lista los horarios laborales. Permite filtrar por codigo_barbero, dia_semana y estado.",
        responses={200: HorarioLaboralSerializer(many=True)}
    )
    def get(self, request):
        horarios = HorarioLaboral.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').all()

        codigo_barbero = request.query_params.get('codigo_barbero')
        dia_semana = request.query_params.get('dia_semana')
        estado_filtro = request.query_params.get('estado')

        if codigo_barbero:
            horarios = horarios.filter(codigo_barbero_id=codigo_barbero)
        if dia_semana:
            horarios = horarios.filter(dia_semana=dia_semana.upper())
        if estado_filtro:
            horarios = horarios.filter(estado=estado_filtro.upper())

        registrar_bitacora(request, 'CONSULTAR_HORARIOS_LABORALES', 'Consulta de horarios laborales.')
        return Response(HorarioLaboralSerializer(horarios, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear horario laboral",
        description="Crea un horario laboral para un usuario con rol Barbero.",
        request=HorarioLaboralSerializer,
        responses={
            201: OpenApiResponse(description="Horario laboral registrado."),
            400: OpenApiResponse(description="Datos invalidos o cruce de horario."),
        },
        examples=[
            OpenApiExample(
                "Crear horario laboral",
                value={
                    "codigo_barbero": "BARB001",
                    "dia_semana": "LUNES",
                    "hora_inicio": "09:00:00",
                    "hora_fin": "18:00:00",
                    "hora_inicio_descanso": "13:00:00",
                    "hora_fin_descanso": "14:00:00",
                    "estado": "ACTIVO",
                    "observacion": "Horario regular de atencion",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = HorarioLaboralSerializer(data=request.data)
        if serializer.is_valid():
            horario = serializer.save()
            registrar_bitacora(
                request,
                'CREAR_HORARIO_LABORAL',
                f'Horario laboral creado para {horario.codigo_barbero.codigo} el {horario.dia_semana}.'
            )
            return Response(
                {'mensaje': 'Horario laboral registrado correctamente.', 'horario': HorarioLaboralSerializer(horario).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU8 - Gestionar Horarios Laborales"])
class HorarioLaboralDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_horario(self, id_horario):
        try:
            return HorarioLaboral.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').get(pk=id_horario)
        except HorarioLaboral.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de horario laboral",
        responses={200: HorarioLaboralSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, id_horario):
        horario = self._get_horario(id_horario)
        if not horario:
            return Response({'error': 'Horario laboral no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(HorarioLaboralSerializer(horario).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar horario laboral",
        request=HorarioLaboralSerializer,
        responses={
            200: OpenApiResponse(description="Horario laboral actualizado."),
            400: OpenApiResponse(description="Datos invalidos o cruce de horario."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def put(self, request, id_horario):
        horario = self._get_horario(id_horario)
        if not horario:
            return Response({'error': 'Horario laboral no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = HorarioLaboralSerializer(horario, data=request.data, partial=True)
        if serializer.is_valid():
            horario = serializer.save()
            registrar_bitacora(
                request,
                'ACTUALIZAR_HORARIO_LABORAL',
                f'Horario laboral actualizado: {horario.id_horario}.'
            )
            return Response(
                {'mensaje': 'Horario laboral actualizado correctamente.', 'horario': HorarioLaboralSerializer(horario).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar horario laboral",
        description="No elimina el registro; lo deja como INACTIVO para conservar historial.",
        responses={200: OpenApiResponse(description="Horario laboral desactivado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def delete(self, request, id_horario):
        horario = self._get_horario(id_horario)
        if not horario:
            return Response({'error': 'Horario laboral no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        horario.estado = 'INACTIVO'
        horario.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_bitacora(request, 'DESACTIVAR_HORARIO_LABORAL', f'Horario laboral desactivado: {horario.id_horario}.')
        return Response({'mensaje': 'Horario laboral desactivado correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU8 - Gestionar Horarios Laborales"])
class HorarioBarberoListView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar horarios de un barbero",
        responses={200: HorarioLaboralSerializer(many=True), 404: OpenApiResponse(description="Barbero no encontrado.")}
    )
    def get(self, request, codigo):
        barbero = Usuario.objects.select_related('id_rol').filter(codigo=codigo, id_rol__nombre__iexact='barbero').first()
        if not barbero:
            return Response({'error': 'Barbero no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        horarios = HorarioLaboral.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').filter(codigo_barbero=barbero)
        registrar_bitacora(request, 'CONSULTAR_HORARIOS_BARBERO', f'Consulta de horarios del barbero {barbero.codigo}.')
        return Response(HorarioLaboralSerializer(horarios, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU8 - Gestionar Bloqueos de Horario"])
class BloqueoHorarioListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar bloqueos de horario",
        description="Lista bloqueos temporales. Permite filtrar por codigo_barbero, fecha y estado.",
        responses={200: BloqueoHorarioSerializer(many=True)}
    )
    def get(self, request):
        bloqueos = BloqueoHorario.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').all()

        codigo_barbero = request.query_params.get('codigo_barbero')
        fecha = request.query_params.get('fecha')
        estado_filtro = request.query_params.get('estado')

        if codigo_barbero:
            bloqueos = bloqueos.filter(codigo_barbero_id=codigo_barbero)
        if fecha:
            bloqueos = bloqueos.filter(fecha=fecha)
        if estado_filtro:
            bloqueos = bloqueos.filter(estado=estado_filtro.upper())

        registrar_bitacora(request, 'CONSULTAR_BLOQUEOS_HORARIO', 'Consulta de bloqueos de horario.')
        return Response(BloqueoHorarioSerializer(bloqueos, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear bloqueo de horario",
        description="Bloquea un rango de horas para un barbero en una fecha especifica.",
        request=BloqueoHorarioSerializer,
        responses={
            201: OpenApiResponse(description="Bloqueo registrado."),
            400: OpenApiResponse(description="Datos invalidos o cruce de bloqueo."),
        },
        examples=[
            OpenApiExample(
                "Crear bloqueo",
                value={
                    "codigo_barbero": "BARB001",
                    "fecha": "2026-05-15",
                    "hora_inicio": "10:00:00",
                    "hora_fin": "12:00:00",
                    "motivo": "Permiso personal",
                    "estado": "ACTIVO",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = BloqueoHorarioSerializer(data=request.data)
        if serializer.is_valid():
            bloqueo = serializer.save()
            registrar_bitacora(
                request,
                'CREAR_BLOQUEO_HORARIO',
                f'Bloqueo creado para {bloqueo.codigo_barbero.codigo} el {bloqueo.fecha}.'
            )
            return Response(
                {'mensaje': 'Bloqueo de horario registrado correctamente.', 'bloqueo': BloqueoHorarioSerializer(bloqueo).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU8 - Gestionar Bloqueos de Horario"])
class BloqueoHorarioDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_bloqueo(self, id_bloqueo):
        try:
            return BloqueoHorario.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').get(pk=id_bloqueo)
        except BloqueoHorario.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de bloqueo",
        responses={200: BloqueoHorarioSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, id_bloqueo):
        bloqueo = self._get_bloqueo(id_bloqueo)
        if not bloqueo:
            return Response({'error': 'Bloqueo de horario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BloqueoHorarioSerializer(bloqueo).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar bloqueo de horario",
        request=BloqueoHorarioSerializer,
        responses={
            200: OpenApiResponse(description="Bloqueo actualizado."),
            400: OpenApiResponse(description="Datos invalidos o cruce de bloqueo."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def put(self, request, id_bloqueo):
        bloqueo = self._get_bloqueo(id_bloqueo)
        if not bloqueo:
            return Response({'error': 'Bloqueo de horario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BloqueoHorarioSerializer(bloqueo, data=request.data, partial=True)
        if serializer.is_valid():
            bloqueo = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_BLOQUEO_HORARIO', f'Bloqueo actualizado: {bloqueo.id_bloqueo}.')
            return Response(
                {'mensaje': 'Bloqueo de horario actualizado correctamente.', 'bloqueo': BloqueoHorarioSerializer(bloqueo).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar bloqueo de horario",
        description="No elimina el registro; lo deja como INACTIVO.",
        responses={200: OpenApiResponse(description="Bloqueo desactivado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def delete(self, request, id_bloqueo):
        bloqueo = self._get_bloqueo(id_bloqueo)
        if not bloqueo:
            return Response({'error': 'Bloqueo de horario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        bloqueo.estado = 'INACTIVO'
        bloqueo.save(update_fields=['estado'])
        registrar_bitacora(request, 'DESACTIVAR_BLOQUEO_HORARIO', f'Bloqueo desactivado: {bloqueo.id_bloqueo}.')
        return Response({'mensaje': 'Bloqueo de horario desactivado correctamente.'}, status=status.HTTP_200_OK)


# CU9 - Gestionar asistencia

@extend_schema(tags=["CU9 - Gestionar Asistencia"])
class AsistenciaBarberoListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar asistencia de barberos",
        description="Lista la asistencia por fecha. Si no se envia fecha, muestra la fecha actual.",
        responses={200: AsistenciaBarberoSerializer(many=True)}
    )
    def get(self, request):
        fecha = request.query_params.get('fecha') or timezone.localdate()
        codigo_barbero = request.query_params.get('codigo_barbero')
        estado_filtro = request.query_params.get('estado')

        asistencias = AsistenciaBarbero.objects.select_related(
            'codigo_barbero',
            'codigo_barbero__id_rol'
        ).filter(fecha=fecha)

        if codigo_barbero:
            asistencias = asistencias.filter(codigo_barbero_id=codigo_barbero)
        if estado_filtro:
            asistencias = asistencias.filter(estado=estado_filtro.upper())

        registrar_bitacora(request, 'CONSULTAR_ASISTENCIAS', f'Consulta de asistencia para fecha {fecha}.')
        return Response(AsistenciaBarberoSerializer(asistencias, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Registrar asistencia de barbero",
        description="Registra asistencia diaria de un barbero. Solo puede existir un registro por barbero y fecha.",
        request=AsistenciaBarberoSerializer,
        responses={
            201: OpenApiResponse(description="Asistencia registrada."),
            400: OpenApiResponse(description="Datos invalidos o asistencia duplicada."),
        },
        examples=[
            OpenApiExample(
                "Registrar presente",
                value={
                    "codigo_barbero": "BARB001",
                    "fecha": "2026-05-10",
                    "estado": "PRESENTE",
                    "hora_entrada": "09:00:00",
                    "hora_salida": "18:00:00",
                    "observacion": "Asistencia normal",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Registrar ausencia",
                value={
                    "codigo_barbero": "BARB001",
                    "fecha": "2026-05-10",
                    "estado": "AUSENTE",
                    "observacion": "No asistio",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = AsistenciaBarberoSerializer(data=request.data)
        if serializer.is_valid():
            asistencia = serializer.save()
            registrar_bitacora(
                request,
                'REGISTRAR_ASISTENCIA',
                f'Asistencia registrada para {asistencia.codigo_barbero.codigo} en fecha {asistencia.fecha}: {asistencia.estado}.'
            )
            return Response(
                {'mensaje': 'Asistencia registrada correctamente.', 'asistencia': AsistenciaBarberoSerializer(asistencia).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU9 - Gestionar Asistencia"])
class AsistenciaBarberoDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_asistencia(self, id_asistencia):
        try:
            return AsistenciaBarbero.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').get(pk=id_asistencia)
        except AsistenciaBarbero.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de asistencia",
        responses={200: AsistenciaBarberoSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_asistencia):
        asistencia = self._get_asistencia(id_asistencia)
        if not asistencia:
            return Response({'error': 'Asistencia no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AsistenciaBarberoSerializer(asistencia).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar asistencia",
        request=AsistenciaBarberoSerializer,
        responses={
            200: OpenApiResponse(description="Asistencia actualizada."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_asistencia):
        asistencia = self._get_asistencia(id_asistencia)
        if not asistencia:
            return Response({'error': 'Asistencia no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AsistenciaBarberoSerializer(asistencia, data=request.data, partial=True)
        if serializer.is_valid():
            asistencia = serializer.save()
            registrar_bitacora(
                request,
                'ACTUALIZAR_ASISTENCIA',
                f'Asistencia actualizada: {asistencia.id_asistencia}.'
            )
            return Response(
                {'mensaje': 'Asistencia actualizada correctamente.', 'asistencia': AsistenciaBarberoSerializer(asistencia).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Eliminar asistencia",
        responses={200: OpenApiResponse(description="Asistencia eliminada."), 404: OpenApiResponse(description="No encontrada.")}
    )
    def delete(self, request, id_asistencia):
        asistencia = self._get_asistencia(id_asistencia)
        if not asistencia:
            return Response({'error': 'Asistencia no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        detalle = f'{asistencia.codigo_barbero.codigo} - {asistencia.fecha}'
        asistencia.delete()
        registrar_bitacora(request, 'ELIMINAR_ASISTENCIA', f'Asistencia eliminada: {detalle}.')
        return Response({'mensaje': 'Asistencia eliminada correctamente.'}, status=status.HTTP_200_OK)
