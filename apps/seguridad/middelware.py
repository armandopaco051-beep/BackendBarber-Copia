from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from .authentication import obtener_usuario_desde_token


class UsuarioActualMiddleware:
    """
    Middleware que decodifica el JWT y adjunta el objeto Usuario
    en request.usuario_actual para usar en los permisos.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.usuario_actual = None

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token_str = auth_header.split(' ')[1]
            try:
                token = AccessToken(token_str)
                request.usuario_actual = obtener_usuario_desde_token(token.payload)
            except TokenError:
                pass  # Token inválido o expirado → usuario_actual queda None

        return self.get_response(request)
