from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .models import Usuario


class UsuarioJWTAuthentication(BaseAuthentication):
    """
    Autenticacion JWT para el modelo propio Usuario.
    SimpleJWT por defecto busca el User de Django; este proyecto usa Usuario.
    """

    keyword = 'Bearer'

    def authenticate(self, request):
        header = get_authorization_header(request).decode('utf-8')
        if not header:
            return None

        parts = header.split()
        if len(parts) == 3 and parts[0].lower() == self.keyword.lower() and parts[1].lower() == self.keyword.lower():
            token_value = parts[2]
        elif len(parts) == 2 and parts[0].lower() == self.keyword.lower():
            token_value = parts[1]
        else:
            raise AuthenticationFailed('Formato de Authorization invalido. Use: Bearer <token>.')

        try:
            token = AccessToken(token_value)
        except TokenError:
            raise AuthenticationFailed('Token invalido o expirado.')

        usuario = obtener_usuario_desde_token(token.payload)
        if not usuario:
            raise AuthenticationFailed('Usuario del token no encontrado.')

        request.usuario_actual = usuario
        return (usuario, token)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


class UsuarioJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'apps.seguridad.authentication.UsuarioJWTAuthentication'
    name = 'BearerAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }


def generar_tokens(usuario: Usuario) -> dict:
    """
    Genera access y refresh token para el usuario del sistema propio.
    El payload incluye: codigo, nombre, apellido, rol.
    """
    refresh = RefreshToken()

    # ── Payload personalizado ──────────────────────────────────────────────
    refresh['codigo'] = usuario.codigo
    refresh['nombre'] = usuario.nombre
    refresh['apellido'] = usuario.apellido
    refresh['rol'] = usuario.id_rol.nombre
    refresh['id_rol'] = usuario.id_rol.id

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'usuario': {
            'codigo': usuario.codigo,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'correo': usuario.correo,
            'rol': usuario.id_rol.nombre,
        }
    }


def obtener_usuario_desde_token(token_payload: dict):
    """
    Recupera el objeto Usuario a partir del payload del JWT.
    Usado en el middleware de autenticación.
    """
    codigo = token_payload.get('codigo')
    if not codigo:
        return None
    try:
        return Usuario.objects.select_related('id_rol').get(codigo=codigo)
    except Usuario.DoesNotExist:
        return None
