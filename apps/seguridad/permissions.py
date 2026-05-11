from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Rol, Usuario


class EsAdmin(BasePermission):
    """
    Solo el Administrador (A1) puede acceder.
    Usado en: CU3, CU4, CU5
    """
    message = "Solo el Administrador tiene permiso para esta acción."

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario:
            return False
        return usuario.es_admin


class EsAdminOConfiguracionInicial(BasePermission):
    """
    Permite inicializar el sistema desde Swagger cuando aun no existen datos.
    Luego de crear el primer usuario, solo Administrador puede acceder.
    """
    message = "Solo el Administrador tiene permiso para esta accion."

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        if usuario and usuario.es_admin:
            return True

        if request.method != 'POST':
            return False

        view_name = view.__class__.__name__

        if view_name == 'RolListCreateView':
            return not Rol.objects.exists()

        if view_name == 'UsuarioListCreateView':
            if Usuario.objects.exists():
                return False
            id_rol = request.data.get('id_rol')
            if not id_rol:
                return False
            return Rol.objects.filter(id=id_rol, nombre__iexact='administrador').exists()

        return False


class EsAdminOBarbero(BasePermission):
    """
    Administrador (A1) o Barbero (A2) pueden acceder.
    """
    message = "Solo Administradores o Barberos tienen permiso."

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario:
            return False
        return usuario.es_admin or usuario.es_barbero


class EsCualquierUsuario(BasePermission):
    """
    Cualquier usuario autenticado (A1, A2, A3) puede acceder.
    """
    def has_permission(self, request, view):
        return getattr(request, 'usuario_actual', None) is not None


class EsAdminOLecturaAutenticada(BasePermission):
    """
    Permite que cualquier usuario autenticado haga consultas GET.
    Para crear, editar o eliminar exige Administrador.
    """
    message = "Solo el Administrador puede modificar esta informacion."

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario:
            return False
        if request.method in SAFE_METHODS:
            return True
        return usuario.es_admin
