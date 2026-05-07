from django.urls import path
from .views import (
    LoginView,
    LogoutView,
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

    # ── CU2: Cerrar sesión ───────────────────────────────────────────────────
    path('logout/', LogoutView.as_view(), name='logout'),

    # ── CU3: Gestionar usuarios ──────────────────────────────────────────────
    path('usuarios/', UsuarioListCreateView.as_view(), name='usuario-list-create'),
    path('usuarios/<str:codigo>/', UsuarioDetalleView.as_view(), name='usuario-detalle'),

    # ── CU4: Gestionar roles ─────────────────────────────────────────────────
    path('roles/', RolListCreateView.as_view(), name='rol-list-create'),
    path('roles/<int:id>/', RolDetalleView.as_view(), name='rol-detalle'),

    # ── CU5: Gestionar barberos ──────────────────────────────────────────────
    path('barberos/', BarberoListCreateView.as_view(), name='barbero-list-create'),
    path('barberos/<str:codigo>/', BarberoDetalleView.as_view(), name='barbero-detalle'),
]