from django.urls import path

from .views import (
    AtencionAgregarServiciosView,
    AtencionCancelarView,
    AtencionDetalleView,
    AtencionFinalizarView,
    AtencionIniciarView,
    AtencionNoAsistioView,
    AtencionPendienteListView,
    AtencionServicioListView,
    BarberoServicioDetalleView,
    BarberoServicioListCreateView,
    CitaAgregarServiciosView,
    CitaDetalleView,
    CitaListCreateView,
    DisponibilidadBarberoView,
    EstadoCitaListView,
    HistorialEstadoCitaListView,
    PromocionDetalleView,
    PromocionListCreateView,
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
    path('citas/<int:id_cita>/servicios/', CitaAgregarServiciosView.as_view(), name='cita-agregar-servicios'),
    path('citas/<int:id_cita>/historial/', HistorialEstadoCitaListView.as_view(), name='cita-historial'),
    path('atenciones/', AtencionServicioListView.as_view(), name='atencion-list'),
    path('atenciones/pendientes/', AtencionPendienteListView.as_view(), name='atencion-pendientes'),
    path('atenciones/iniciar/', AtencionIniciarView.as_view(), name='atencion-iniciar'),
    path('atenciones/<int:id_atencion>/', AtencionDetalleView.as_view(), name='atencion-detalle'),
    path('atenciones/<int:id_atencion>/servicios/', AtencionAgregarServiciosView.as_view(), name='atencion-agregar-servicios'),
    path('atenciones/<int:id_atencion>/finalizar/', AtencionFinalizarView.as_view(), name='atencion-finalizar'),
    path('atenciones/<int:id_atencion>/no-asistio/', AtencionNoAsistioView.as_view(), name='atencion-no-asistio'),
    path('atenciones/<int:id_atencion>/cancelar/', AtencionCancelarView.as_view(), name='atencion-cancelar'),
    path('promociones/', PromocionListCreateView.as_view(), name='promocion-list-create'),
    path('promociones/<int:id_promocion>/', PromocionDetalleView.as_view(), name='promocion-detalle'),
    path('disponibilidad/', DisponibilidadBarberoView.as_view(), name='cita-disponibilidad'),
]
