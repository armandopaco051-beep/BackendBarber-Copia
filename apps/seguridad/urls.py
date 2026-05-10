from django.urls import path
from .views import (
    AsistenciaBarberoDetalleView,
    AsistenciaBarberoListCreateView,
    LoginView,
    RegistroClienteView,
    LogoutView,
    SolicitarRecuperacionView,
    ValidarCodigoRecuperacionView,
    RestablecerPasswordView,
    BitacoraListView,
    BloqueoHorarioDetalleView,
    BloqueoHorarioListCreateView,
    HorarioBarberoListView,
    HorarioLaboralDetalleView,
    HorarioLaboralListCreateView,
    UsuarioListCreateView,
    UsuarioDetalleView,
    RolListCreateView,
    RolDetalleView,
    BarberoListCreateView,
    BarberoDetalleView,
)

urlpatterns = [

    # ── CU1: Iniciar sesión ──────────────────────────────────────────────────
    path('login/', LoginView.as_view(), name='login'),
    path('registro-cliente/', RegistroClienteView.as_view(), name='registro-cliente'),
    path('solicitar-recuperacion/', SolicitarRecuperacionView.as_view(), name='solicitar-recuperacion'),
    path('validar-codigo-recuperacion/', ValidarCodigoRecuperacionView.as_view(), name='validar-codigo-recuperacion'),
    path('restablecer-password/', RestablecerPasswordView.as_view(), name='restablecer-password'),
    path('password/solicitar-codigo/', SolicitarRecuperacionView.as_view(), name='password-solicitar-codigo'),
    path('password/validar-codigo/', ValidarCodigoRecuperacionView.as_view(), name='password-validar-codigo'),
    path('password/restablecer/', RestablecerPasswordView.as_view(), name='password-restablecer'),

    # ── CU2: Cerrar sesión ───────────────────────────────────────────────────
    path('logout/', LogoutView.as_view(), name='logout'),
    path('bitacora/', BitacoraListView.as_view(), name='bitacora-list'),

    # ── CU3: Gestionar usuarios ──────────────────────────────────────────────
    path('usuarios/', UsuarioListCreateView.as_view(), name='usuario-list-create'),
    path('usuarios/<str:codigo>/', UsuarioDetalleView.as_view(), name='usuario-detalle'),

    # ── CU4: Gestionar roles ─────────────────────────────────────────────────
    path('roles/', RolListCreateView.as_view(), name='rol-list-create'),
    path('roles/<int:id>/', RolDetalleView.as_view(), name='rol-detalle'),

    # ── CU5: Gestionar barberos ──────────────────────────────────────────────
    path('barberos/', BarberoListCreateView.as_view(), name='barbero-list-create'),
    path('barberos/<str:codigo>/horarios/', HorarioBarberoListView.as_view(), name='barbero-horarios'),
    path('barberos/<str:codigo>/', BarberoDetalleView.as_view(), name='barbero-detalle'),

    # CU8: Gestionar horarios laborales
    path('horarios-laborales/', HorarioLaboralListCreateView.as_view(), name='horario-laboral-list-create'),
    path('horarios-laborales/<int:id_horario>/', HorarioLaboralDetalleView.as_view(), name='horario-laboral-detalle'),
    path('bloqueos-horario/', BloqueoHorarioListCreateView.as_view(), name='bloqueo-horario-list-create'),
    path('bloqueos-horario/<int:id_bloqueo>/', BloqueoHorarioDetalleView.as_view(), name='bloqueo-horario-detalle'),

    # CU9: Gestionar asistencia
    path('asistencias/', AsistenciaBarberoListCreateView.as_view(), name='asistencia-barbero-list-create'),
    path('asistencias/<int:id_asistencia>/', AsistenciaBarberoDetalleView.as_view(), name='asistencia-barbero-detalle'),
]
