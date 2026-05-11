from django.urls import path

from .views import (
    ClienteCitaDetalleView,
    ClienteCitaListCreateView,
    ClienteDashboardView,
    ClienteDisponibilidadView,
)


# Rutas para la vista cliente del Ciclo 2.
urlpatterns = [
    path('dashboard/', ClienteDashboardView.as_view(), name='cliente-dashboard'),
    path('disponibilidad/', ClienteDisponibilidadView.as_view(), name='cliente-disponibilidad'),
    path('citas/', ClienteCitaListCreateView.as_view(), name='cliente-cita-list-create'),
    path('citas/<int:id_cita>/', ClienteCitaDetalleView.as_view(), name='cliente-cita-detalle'),
]
