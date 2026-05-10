from django.urls import path

from .views import CambiarPasswordPerfilView, PerfilUsuarioView

from apps.seguridad.views import (
    BarberoDetalleView,
    BarberoListCreateView,
    BitacoraListView,
    LoginView,
    LogoutView,
    RegistroClienteView,
    RestablecerPasswordView,
    RolDetalleView,
    RolListCreateView,
    SolicitarRecuperacionView,
    UsuarioDetalleView,
    UsuarioListCreateView,
    ValidarCodigoRecuperacionView,
)


# Rutas del paquete usuario.
# Algunas vistas se reutilizan desde apps.seguridad para mantener compatibilidad
# mientras se migra el proyecto por paquetes.
urlpatterns = [
    # Autenticacion y recuperacion de contrasena.
    path('login/', LoginView.as_view(), name='usuario-login'),
    path('logout/', LogoutView.as_view(), name='usuario-logout'),
    path('registro-cliente/', RegistroClienteView.as_view(), name='usuario-registro-cliente'),
    path('password/solicitar-codigo/', SolicitarRecuperacionView.as_view(), name='usuario-password-solicitar-codigo'),
    path('password/validar-codigo/', ValidarCodigoRecuperacionView.as_view(), name='usuario-password-validar-codigo'),
    path('password/restablecer/', RestablecerPasswordView.as_view(), name='usuario-password-restablecer'),

    # Perfil del usuario autenticado.
    path('perfil/', PerfilUsuarioView.as_view(), name='usuario-perfil'),
    path('perfil/password/', CambiarPasswordPerfilView.as_view(), name='usuario-perfil-password'),

    # CRUD administrativo.
    path('usuarios/', UsuarioListCreateView.as_view(), name='usuario-list-create'),
    path('usuarios/<str:codigo>/', UsuarioDetalleView.as_view(), name='usuario-detalle'),
    path('roles/', RolListCreateView.as_view(), name='usuario-rol-list-create'),
    path('roles/<int:id>/', RolDetalleView.as_view(), name='usuario-rol-detalle'),
    path('barberos/', BarberoListCreateView.as_view(), name='usuario-barbero-list-create'),
    path('barberos/<str:codigo>/', BarberoDetalleView.as_view(), name='usuario-barbero-detalle'),
    path('bitacora/', BitacoraListView.as_view(), name='usuario-bitacora-list'),
]
