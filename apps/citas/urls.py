from django.urls import path

from .views import (
    BarberoServicioDetalleView,
    BarberoServicioListCreateView,
    CitaDetalleView,
    CitaListCreateView,
    DisponibilidadBarberoView,
    EstadoCitaListView,
    HistorialEstadoCitaListView,
)

from apps.seguridad.views import (
    AsistenciaBarberoDetalleView,
    AsistenciaBarberoListCreateView,
    BloqueoHorarioDetalleView,
    BloqueoHorarioListCreateView,
    HorarioBarberoListView,
    HorarioLaboralDetalleView,
    HorarioLaboralListCreateView,
)


# Rutas del paquete citas.
# Incluye CU8 horarios, CU9 asistencia y CU11 gestion de citas.
urlpatterns = [
    # CU8: horarios laborales y bloqueos de horario.
    path('horarios-laborales/', HorarioLaboralListCreateView.as_view(), name='citas-horario-laboral-list-create'),
    path('horarios-laborales/<int:id_horario>/', HorarioLaboralDetalleView.as_view(), name='citas-horario-laboral-detalle'),
    path('barberos/<str:codigo>/horarios/', HorarioBarberoListView.as_view(), name='citas-barbero-horarios'),
    path('bloqueos-horario/', BloqueoHorarioListCreateView.as_view(), name='citas-bloqueo-horario-list-create'),
    path('bloqueos-horario/<int:id_bloqueo>/', BloqueoHorarioDetalleView.as_view(), name='citas-bloqueo-horario-detalle'),

    # CU9: asistencia diaria de barberos.
    path('asistencias/', AsistenciaBarberoListCreateView.as_view(), name='citas-asistencia-list-create'),
    path('asistencias/<int:id_asistencia>/', AsistenciaBarberoDetalleView.as_view(), name='citas-asistencia-detalle'),

    # CU11: estados, barbero-servicio, citas, historial y disponibilidad.
    path('estados-cita/', EstadoCitaListView.as_view(), name='cita-estados-list'),
    path('barbero-servicios/', BarberoServicioListCreateView.as_view(), name='barbero-servicio-list-create'),
    path('barbero-servicios/<int:id_barbero_servicio>/', BarberoServicioDetalleView.as_view(), name='barbero-servicio-detalle'),
    path('citas/', CitaListCreateView.as_view(), name='cita-list-create'),
    path('citas/<int:id_cita>/', CitaDetalleView.as_view(), name='cita-detalle'),
    path('citas/<int:id_cita>/historial/', HistorialEstadoCitaListView.as_view(), name='cita-historial'),
    path('disponibilidad/', DisponibilidadBarberoView.as_view(), name='cita-disponibilidad'),
]
