from django.urls import path

from .views import (
    AsignacionEstacionTrabajoActivarView,
    AsignacionEstacionTrabajoDetalleView,
    AsignacionEstacionTrabajoListCreateView,
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
    BarberosActivosEstacionView,
    CitaAgregarServiciosView,
    CitaDetalleView,
    CitaListCreateView,
    DisponibilidadBarberoView,
    EstadoCitaListView,
    EstacionTrabajoActivarView,
    EstacionTrabajoDetalleView,
    EstacionTrabajoListCreateView,
    EstacionesDisponiblesAsignacionView,
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

    # CU26: estaciones de trabajo.
    # GET/POST lista o registra estaciones; GET/PUT/DELETE gestiona una estacion;
    # POST activar permite volver a habilitar una estacion inactiva.
    path('estaciones-trabajo/', EstacionTrabajoListCreateView.as_view(), name='estacion-trabajo-list-create'),
    path('estaciones-trabajo/<int:id_estacion>/', EstacionTrabajoDetalleView.as_view(), name='estacion-trabajo-detalle'),
    path('estaciones-trabajo/<int:id_estacion>/activar/', EstacionTrabajoActivarView.as_view(), name='estacion-trabajo-activar'),

    # CU27: asignacion de barberos a estaciones.
    # Incluye endpoints de apoyo para seleccionar barberos y estaciones disponibles.
    # barberos-activos: llena el selector de barberos.
    # estaciones-disponibles: llena el selector de estaciones libres para un turno.
    # asignaciones-estaciones: registra y consulta las asignaciones creadas.
    path('asignaciones-estaciones/barberos-activos/', BarberosActivosEstacionView.as_view(), name='asignacion-estacion-barberos-activos'),
    path('asignaciones-estaciones/estaciones-disponibles/', EstacionesDisponiblesAsignacionView.as_view(), name='asignacion-estacion-estaciones-disponibles'),
    path('asignaciones-estaciones/', AsignacionEstacionTrabajoListCreateView.as_view(), name='asignacion-estacion-list-create'),
    path('asignaciones-estaciones/<int:id_asignacion>/', AsignacionEstacionTrabajoDetalleView.as_view(), name='asignacion-estacion-detalle'),
    path('asignaciones-estaciones/<int:id_asignacion>/activar/', AsignacionEstacionTrabajoActivarView.as_view(), name='asignacion-estacion-activar'),
    path('disponibilidad/', DisponibilidadBarberoView.as_view(), name='cita-disponibilidad'),
]
