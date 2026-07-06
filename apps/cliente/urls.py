from django.urls import path

from .views import (
    ClienteCitaDetalleView,
    ClienteCitaListCreateView,
    ClienteDashboardView,
    ClienteDisponibilidadView,
    EncuestaSatisfaccionActivarView,
    EncuestaSatisfaccionDetalleView,
    EncuestaSatisfaccionListCreateView,
    ReclamoSugerenciaDetalleView,
    ReclamoSugerenciaListCreateView,
    RespuestaReclamoSugerenciaView,
)


# Rutas para la vista cliente del Ciclo 2.
urlpatterns = [
    path('dashboard/', ClienteDashboardView.as_view(), name='cliente-dashboard'),
    path('disponibilidad/', ClienteDisponibilidadView.as_view(), name='cliente-disponibilidad'),
    path('citas/', ClienteCitaListCreateView.as_view(), name='cliente-cita-list-create'),
    path('citas/<int:id_cita>/', ClienteCitaDetalleView.as_view(), name='cliente-cita-detalle'),

    # CU30: gestion administrativa de encuestas de satisfaccion.
    path('encuestas/', EncuestaSatisfaccionListCreateView.as_view(), name='encuesta-satisfaccion-list-create'),
    path('encuestas/<int:id_encuesta>/', EncuestaSatisfaccionDetalleView.as_view(), name='encuesta-satisfaccion-detalle'),
    path('encuestas/<int:id_encuesta>/activar/', EncuestaSatisfaccionActivarView.as_view(), name='encuesta-satisfaccion-activar'),

    # CU31: reclamos y sugerencias de clientes.
    path('reclamos-sugerencias/', ReclamoSugerenciaListCreateView.as_view(), name='reclamo-sugerencia-list-create'),
    path('reclamos-sugerencias/<int:id_solicitud>/', ReclamoSugerenciaDetalleView.as_view(), name='reclamo-sugerencia-detalle'),
    path('reclamos-sugerencias/<int:id_solicitud>/responder/', RespuestaReclamoSugerenciaView.as_view(), name='reclamo-sugerencia-responder'),
]
