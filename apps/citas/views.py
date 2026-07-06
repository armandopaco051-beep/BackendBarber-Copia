from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date, parse_time
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.models import AsistenciaBarbero, BloqueoHorario, HorarioLaboral, Usuario
from apps.seguridad.permissions import EsAdmin, EsAdminOBarbero
from apps.seguridad.views import registrar_bitacora
from apps.servicios.models import Servicio

from .models import AsignacionEstacionTrabajo, AtencionServicio, BarberoServicio, Cita, EstadoCita, EstacionTrabajo, Promocion
from .serializers import (
    AsignacionEstacionTrabajoSerializer,
    AtencionAgregarServiciosSerializer,
    AtencionCambiarEstadoSerializer,
    AtencionFinalizarSerializer,
    AtencionIniciarSerializer,
    AtencionServicioSerializer,
    BarberoServicioSerializer,
    BarberoActivoSerializer,
    CitaSerializer,
    DIAS_SEMANA,
    ESTADOS_NO_BLOQUEAN_HORARIO,
    EstadoCitaSerializer,
    EstacionTrabajoSerializer,
    HistorialEstadoCitaSerializer,
    PromocionSerializer,
)
from .services import (
    agregar_servicios_atencion,
    cambiar_estado_atencion,
    finalizar_atencion,
    iniciar_atencion,
)


ESTADOS_ASISTENCIA_NO_DISPONIBLES = ['AUSENTE', 'PERMISO', 'INHABILITADO']
CODIGOS_TODOS_BARBEROS = {'TODOS', 'ANY', 'CUALQUIERA'}


# Funcion auxiliar para sumar minutos a una hora.
# Se usa para calcular bloques disponibles en la agenda.
def sumar_minutos(fecha, hora, minutos):
    return (datetime.combine(fecha, hora) + timedelta(minutes=minutos)).time()


def obtener_query_param(query_params, *nombres):
    # Permite aceptar distintos nombres que puede enviar el frontend.
    # Ejemplo: codigo_barbero, codigoBarbero, barbero.
    for nombre in nombres:
        valor = query_params.get(nombre)
        if valor not in [None, '']:
            return valor
    return None


def parsear_fecha_frontend(valor):
    # Acepta fecha ISO del backend: 2026-05-10.
    fecha = parse_date(valor or '')
    if fecha:
        return fecha

    # Acepta fecha visual del frontend: 10/05/2026.
    try:
        return datetime.strptime(valor or '', '%d/%m/%Y').date()
    except ValueError:
        return None


def parsear_hora_frontend(valor):
    # Acepta HH:MM o HH:MM:SS para filtros de disponibilidad.
    return parse_time(str(valor or ''))


def cruza_intervalo(inicio_a, fin_a, inicio_b, fin_b):
    # Dos rangos se cruzan cuando el inicio de uno es menor al fin del otro y viceversa.
    return inicio_a < fin_b and fin_a > inicio_b


def es_modo_todos_barberos(codigo_barbero):
    return str(codigo_barbero or '').strip().upper() in CODIGOS_TODOS_BARBEROS or str(codigo_barbero or '').strip() == ''


def barbero_habilitado_para_servicio(barbero, servicio):
    asignaciones = BarberoServicio.objects.filter(codigo_barbero=barbero)
    if not asignaciones.exists():
        return True
    return asignaciones.filter(id_servicio=servicio, estado='ACTIVO').exists()


def barbero_habilitado_para_servicios(barbero, servicios):
    return all(barbero_habilitado_para_servicio(barbero, servicio) for servicio in servicios)


def consultar_horarios_barbero(barbero, fecha):
    dia_semana = DIAS_SEMANA[fecha.weekday()]
    return HorarioLaboral.objects.filter(
        codigo_barbero=barbero,
        dia_semana__iexact=dia_semana,
        estado__iexact='ACTIVO'
    ).order_by('hora_inicio')


def consultar_asistencia_barbero(barbero, fecha):
    return AsistenciaBarbero.objects.filter(codigo_barbero=barbero, fecha=fecha).first()


def consultar_bloqueos_barbero(barbero, fecha):
    return list(BloqueoHorario.objects.filter(
        codigo_barbero=barbero,
        fecha=fecha,
        estado__iexact='ACTIVO',
    ).values('hora_inicio', 'hora_fin'))


def consultar_citas_barbero(barbero, fecha):
    return list(Cita.objects.select_related('id_estadoc').filter(
        codigo_barbero=barbero,
        fecha=fecha,
    ).exclude(id_estadoc__nombre__in=ESTADOS_NO_BLOQUEAN_HORARIO).values('hora_inicio', 'hora_fin'))


def generar_bloques_horario(fecha, horario, duracion_minutos):
    inicio = datetime.combine(fecha, horario.hora_inicio)
    fin_jornada = datetime.combine(fecha, horario.hora_fin)
    paso = timedelta(minutes=duracion_minutos)

    while inicio + paso <= fin_jornada:
        yield inicio.time(), (inicio + paso).time()
        inicio += paso


def calcular_disponibilidad_barbero(barbero, servicios, fecha):
    duracion_total = sum(servicio.duracion_minutos for servicio in servicios)
    if duracion_total <= 0:
        return {'disponibles': [], 'mensaje': 'El servicio no tiene una duracion valida.'}

    if not barbero_habilitado_para_servicios(barbero, servicios):
        return {'disponibles': [], 'mensaje': 'El barbero seleccionado no tiene habilitados todos los servicios.'}

    asistencia = consultar_asistencia_barbero(barbero, fecha)
    estado_asistencia = str(getattr(asistencia, 'estado', '')).upper()
    if asistencia and estado_asistencia in ESTADOS_ASISTENCIA_NO_DISPONIBLES:
        return {'disponibles': [], 'mensaje': 'El barbero no esta disponible para la fecha seleccionada.'}

    horarios = consultar_horarios_barbero(barbero, fecha)
    if not horarios.exists():
        return {'disponibles': [], 'mensaje': 'El barbero no tiene horario laboral activo para la fecha seleccionada.'}

    bloqueos_del_dia = consultar_bloqueos_barbero(barbero, fecha)
    citas_del_dia = consultar_citas_barbero(barbero, fecha)
    disponibles = []

    for horario in horarios:
        for hora_inicio, hora_fin in generar_bloques_horario(fecha, horario, duracion_total):
            cruza_descanso = False
            if horario.hora_inicio_descanso and horario.hora_fin_descanso:
                cruza_descanso = cruza_intervalo(
                    hora_inicio,
                    hora_fin,
                    horario.hora_inicio_descanso,
                    horario.hora_fin_descanso,
                )

            cruza_bloqueo = any(
                cruza_intervalo(hora_inicio, hora_fin, bloqueo['hora_inicio'], bloqueo['hora_fin'])
                for bloqueo in bloqueos_del_dia
            )
            cruza_cita = any(
                cruza_intervalo(hora_inicio, hora_fin, cita['hora_inicio'], cita['hora_fin'])
                for cita in citas_del_dia
            )

            if not cruza_descanso and not cruza_bloqueo and not cruza_cita:
                disponibles.append(hora_inicio.strftime('%H:%M:%S'))

    disponibles = sorted(set(disponibles))
    mensaje = '' if disponibles else 'No hay horarios disponibles para ese barbero, servicio y fecha.'
    return {'disponibles': disponibles, 'mensaje': mensaje}


# Lista los estados posibles de una cita.
# CRUD: solo GET porque los estados base se controlan desde el sistema.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class EstadoCitaListView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar estados de cita",
        responses={200: EstadoCitaSerializer(many=True)}
    )
    def get(self, request):
        estados = EstadoCita.objects.all()
        return Response(EstadoCitaSerializer(estados, many=True).data, status=status.HTTP_200_OK)


# CRUD de servicios habilitados por barbero.
# GET lista habilitaciones y POST crea una nueva relacion barbero-servicio.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class BarberoServicioListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar servicios habilitados por barbero",
        responses={200: BarberoServicioSerializer(many=True)}
    )
    def get(self, request):
        # Filtros para que frontend liste por barbero, servicio o estado.
        asignaciones = BarberoServicio.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol', 'id_servicio').all()
        codigo_barbero = request.query_params.get('codigo_barbero')
        id_servicio = request.query_params.get('id_servicio')
        estado_filtro = request.query_params.get('estado')

        if codigo_barbero:
            asignaciones = asignaciones.filter(codigo_barbero_id=codigo_barbero)
        if id_servicio:
            asignaciones = asignaciones.filter(id_servicio_id=id_servicio)
        if estado_filtro:
            asignaciones = asignaciones.filter(estado=estado_filtro.upper())

        return Response(BarberoServicioSerializer(asignaciones, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Habilitar barbero para servicio",
        request=BarberoServicioSerializer,
        responses={
            201: OpenApiResponse(description="Barbero habilitado para servicio."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Habilitar servicio",
                value={"codigo_barbero": "BARB001", "id_servicio": 1, "estado": "ACTIVO"},
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Habilita un servicio para un barbero y registra bitacora.
        serializer = BarberoServicioSerializer(data=request.data)
        if serializer.is_valid():
            asignacion = serializer.save()
            registrar_bitacora(
                request,
                'HABILITAR_BARBERO_SERVICIO',
                f'Barbero {asignacion.codigo_barbero.codigo} habilitado para servicio {asignacion.id_servicio_id}.'
            )
            return Response(
                {'mensaje': 'Barbero habilitado para servicio correctamente.', 'asignacion': BarberoServicioSerializer(asignacion).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Detalle de la relacion barbero-servicio.
# PUT actualiza y DELETE desactiva la habilitacion.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class BarberoServicioDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_asignacion(self, id_barbero_servicio):
        # Busca la asignacion con barbero y servicio incluidos.
        try:
            return BarberoServicio.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol', 'id_servicio').get(pk=id_barbero_servicio)
        except BarberoServicio.DoesNotExist:
            return None

    @extend_schema(
        summary="Actualizar servicio habilitado por barbero",
        request=BarberoServicioSerializer,
        responses={
            200: BarberoServicioSerializer,
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="Asignacion no encontrada."),
        }
    )
    def put(self, request, id_barbero_servicio):
        asignacion = self._get_asignacion(id_barbero_servicio)
        if not asignacion:
            return Response({'error': 'Asignacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BarberoServicioSerializer(asignacion, data=request.data, partial=True)
        if serializer.is_valid():
            asignacion = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_BARBERO_SERVICIO', f'Asignacion actualizada: {asignacion.id_barbero_servicio}.')
            return Response({'mensaje': 'Asignacion actualizada correctamente.', 'asignacion': BarberoServicioSerializer(asignacion).data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar servicio habilitado por barbero",
        responses={
            200: OpenApiResponse(description="Asignacion desactivada."),
            404: OpenApiResponse(description="Asignacion no encontrada."),
        }
    )
    def delete(self, request, id_barbero_servicio):
        asignacion = self._get_asignacion(id_barbero_servicio)
        if not asignacion:
            return Response({'error': 'Asignacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        asignacion.estado = 'INACTIVO'
        asignacion.save(update_fields=['estado'])
        registrar_bitacora(request, 'DESACTIVAR_BARBERO_SERVICIO', f'Asignacion desactivada: {asignacion.id_barbero_servicio}.')
        return Response({'mensaje': 'Asignacion desactivada correctamente.'}, status=status.HTTP_200_OK)


# CRUD principal de citas.
# GET lista citas por filtros y POST registra una nueva cita.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class CitaListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar citas",
        description="Lista citas. Permite filtrar por fecha, barbero, cliente y estado.",
        responses={200: CitaSerializer(many=True)}
    )
    def get(self, request):
        # Permite filtrar agenda por fecha, barbero, cliente y estado.
        citas = Cita.objects.select_related(
            'codigo_cliente',
            'codigo_cliente__id_rol',
            'codigo_barbero',
            'codigo_barbero__id_rol',
            'id_servicio',
            'id_estadoc',
            'registrado_por',
        ).prefetch_related('servicios_detalle__id_servicio').all()

        fecha = request.query_params.get('fecha')
        codigo_barbero = request.query_params.get('codigo_barbero')
        codigo_cliente = request.query_params.get('codigo_cliente')
        estado_filtro = request.query_params.get('estado')

        if fecha:
            citas = citas.filter(fecha=fecha)
        if codigo_barbero:
            citas = citas.filter(codigo_barbero_id=codigo_barbero)
        if codigo_cliente:
            citas = citas.filter(codigo_cliente_id=codigo_cliente)
        if estado_filtro:
            citas = citas.filter(id_estadoc__nombre=estado_filtro.upper().replace(' ', '_'))

        registrar_bitacora(request, 'CONSULTAR_CITAS', 'Consulta de citas.')
        return Response(CitaSerializer(citas, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Registrar cita",
        request=CitaSerializer,
        responses={
            201: OpenApiResponse(description="Cita registrada."),
            400: OpenApiResponse(description="Datos invalidos o horario no disponible."),
        },
        examples=[
            OpenApiExample(
                "Registrar cita",
                value={
                    "codigo_cliente": "CLIE001",
                    "codigo_barbero": "BARB001",
            "id_servicio": 1,
                    "servicios": [{"id_servicio": 1}, {"id_servicio": 2}],
                    "fecha": "2026-05-15",
                    "hora_inicio": "10:00:00",
                    "estado": "CONFIRMADA",
                    "observacion": "Cliente pidio mid fade con barba perfilada",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Crea cita validando disponibilidad completa desde CitaSerializer.
        serializer = CitaSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            cita = serializer.save()
            registrar_bitacora(request, 'CREAR_CITA', f'Cita registrada: {cita.id_cita}.')
            return Response(
                {'mensaje': 'Cita registrada correctamente.', 'cita': CitaSerializer(cita).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Detalle de una cita.
# GET consulta, PUT actualiza/reprograma/cancela y DELETE anula.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class CitaDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_cita(self, id_cita):
        # Busca cita con todas sus relaciones para evitar consultas repetidas.
        try:
            return Cita.objects.select_related(
                'codigo_cliente',
                'codigo_cliente__id_rol',
                'codigo_barbero',
                'codigo_barbero__id_rol',
                'id_servicio',
                'id_estadoc',
                'registrado_por',
            ).prefetch_related('servicios_detalle__id_servicio').get(pk=id_cita)
        except Cita.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de cita",
        responses={200: CitaSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_cita):
        cita = self._get_cita(id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CitaSerializer(cita).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar, cancelar o reprogramar cita",
        description="Permite cambiar servicio, barbero, fecha, hora, estado, observacion o motivo de cancelacion.",
        request=CitaSerializer,
        responses={
            200: OpenApiResponse(description="Cita actualizada."),
            400: OpenApiResponse(description="Datos invalidos o horario no disponible."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_cita):
        # Si se cambia fecha/hora/barbero/servicio, vuelve a validar disponibilidad.
        cita = self._get_cita(id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CitaSerializer(cita, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            cita = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_CITA', f'Cita actualizada: {cita.id_cita}.')
            return Response({'mensaje': 'Cita actualizada correctamente.', 'cita': CitaSerializer(cita).data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Anular cita",
        description="No elimina la cita; cambia su estado a ANULADA.",
        responses={200: OpenApiResponse(description="Cita anulada."), 404: OpenApiResponse(description="No encontrada.")}
    )
    def delete(self, request, id_cita):
        # No borra fisicamente: cambia el estado a ANULADA.
        cita = self._get_cita(id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CitaSerializer(cita, data={'estado': 'ANULADA'}, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            registrar_bitacora(request, 'ANULAR_CITA', f'Cita anulada: {cita.id_cita}.')
            return Response({'mensaje': 'Cita anulada correctamente.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU11 - Gestionar Citas"])
class CitaAgregarServiciosView(APIView):
    permission_classes = [EsAdmin]

    def _get_cita(self, id_cita):
        try:
            return Cita.objects.select_related(
                'codigo_cliente',
                'codigo_cliente__id_rol',
                'codigo_barbero',
                'codigo_barbero__id_rol',
                'id_servicio',
                'id_estadoc',
                'registrado_por',
            ).prefetch_related('servicios_detalle__id_servicio').get(pk=id_cita)
        except Cita.DoesNotExist:
            return None

    @extend_schema(
        summary="Agregar servicios a una cita",
        description="Agrega servicios adicionales a una cita no cobrada. Recalcula duracion, hora fin y total estimado.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "servicios": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"id_servicio": {"type": "integer"}},
                            "required": ["id_servicio"],
                        },
                    }
                },
                "required": ["servicios"],
            }
        },
        responses={
            200: CitaSerializer,
            400: OpenApiResponse(description="Datos invalidos o cita ya cobrada."),
            404: OpenApiResponse(description="Cita no encontrada."),
        },
        examples=[
            OpenApiExample(
                "Agregar servicios",
                value={"servicios": [{"id_servicio": 2}, {"id_servicio": 3}]},
                request_only=True,
            )
        ]
    )
    def post(self, request, id_cita):
        cita = self._get_cita(id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.ventas_caja.models import Venta

        if Venta.objects.filter(id_cita=cita, estado='PAGADA').exists():
            return Response(
                {'error': 'No se pueden agregar servicios a una cita que ya fue cobrada.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        servicios_nuevos = request.data.get('servicios') or []
        if not servicios_nuevos:
            return Response({'servicios': 'Debe enviar al menos un servicio.'}, status=status.HTTP_400_BAD_REQUEST)

        ids_actuales = [
            detalle.id_servicio_id
            for detalle in cita.servicios_detalle.all()
        ] or [cita.id_servicio_id]
        ids_finales = list(dict.fromkeys(ids_actuales + [
            item.get('id_servicio') for item in servicios_nuevos if item.get('id_servicio')
        ]))

        serializer = CitaSerializer(
            cita,
            data={'servicios': [{'id_servicio': id_servicio} for id_servicio in ids_finales]},
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            cita = serializer.save()
            registrar_bitacora(request, 'AGREGAR_SERVICIOS_CITA', f'Servicios agregados a cita: {cita.id_cita}.')
            return Response(
                {'mensaje': 'Servicios agregados correctamente.', 'cita': CitaSerializer(cita).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionServicioListView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Listar atenciones de servicio",
        description="Administrador ve todas. Barbero ve solo sus atenciones/citas asignadas.",
        responses={200: AtencionServicioSerializer(many=True)}
    )
    def get(self, request):
        usuario = getattr(request, 'usuario_actual', None)
        atenciones = AtencionServicio.objects.select_related(
            'id_cita',
            'id_cita__id_estadoc',
            'codigo_cliente',
            'codigo_barbero',
            'registrado_por',
        ).prefetch_related('detalles__id_servicio').all()

        if usuario and usuario.es_barbero and not usuario.es_admin:
            atenciones = atenciones.filter(codigo_barbero=usuario)

        fecha = request.query_params.get('fecha')
        estado = request.query_params.get('estado')
        codigo_barbero = request.query_params.get('codigo_barbero')
        listo_para_cobro = request.query_params.get('listo_para_cobro')

        if fecha:
            atenciones = atenciones.filter(fecha=fecha)
        if estado:
            atenciones = atenciones.filter(estado=estado.upper())
        if codigo_barbero and usuario.es_admin:
            atenciones = atenciones.filter(codigo_barbero_id=codigo_barbero)
        if listo_para_cobro is not None:
            atenciones = atenciones.filter(listo_para_cobro=str(listo_para_cobro).lower() == 'true')

        return Response(AtencionServicioSerializer(atenciones, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionPendienteListView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Listar citas pendientes de atencion",
        description="Muestra citas que aun no tienen atencion finalizada/cancelada/no asistio.",
        responses={200: CitaSerializer(many=True)}
    )
    def get(self, request):
        usuario = getattr(request, 'usuario_actual', None)
        citas = Cita.objects.select_related(
            'codigo_cliente',
            'codigo_cliente__id_rol',
            'codigo_barbero',
            'codigo_barbero__id_rol',
            'id_servicio',
            'id_estadoc',
            'registrado_por',
        ).prefetch_related('servicios_detalle__id_servicio').exclude(
            id_estadoc__nombre__in=['ANULADA', 'CANCELADA', 'FINALIZADA', 'ATENDIDA', 'NO_ASISTIO']
        ).exclude(
            atencion_servicio__estado__in=['FINALIZADA', 'CANCELADA', 'NO_ASISTIO']
        )

        if usuario and usuario.es_barbero and not usuario.es_admin:
            citas = citas.filter(codigo_barbero=usuario)

        fecha = request.query_params.get('fecha')
        if fecha:
            citas = citas.filter(fecha=fecha)

        return Response(CitaSerializer(citas, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionIniciarView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Iniciar atencion de una cita",
        request=AtencionIniciarSerializer,
        responses={200: AtencionServicioSerializer, 400: OpenApiResponse(description="No se pudo iniciar.")}
    )
    def post(self, request):
        serializer = AtencionIniciarSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            atencion = iniciar_atencion(serializer.validated_data['id_cita'], getattr(request, 'usuario_actual', None))
            registrar_bitacora(request, 'INICIAR_ATENCION', f'Atencion iniciada: {atencion.id_atencion}.')
        except ValidationError as error:
            return Response({'error': error.message_dict if hasattr(error, 'message_dict') else error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'mensaje': 'Atencion iniciada correctamente.', 'atencion': AtencionServicioSerializer(atencion).data})


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionDetalleView(APIView):
    permission_classes = [EsAdminOBarbero]

    def _get_atencion(self, id_atencion, request):
        usuario = getattr(request, 'usuario_actual', None)
        queryset = AtencionServicio.objects.select_related(
            'id_cita',
            'id_cita__id_estadoc',
            'codigo_cliente',
            'codigo_barbero',
            'registrado_por',
        ).prefetch_related('detalles__id_servicio')
        if usuario and usuario.es_barbero and not usuario.es_admin:
            queryset = queryset.filter(codigo_barbero=usuario)
        return queryset.filter(pk=id_atencion).first()

    @extend_schema(summary="Ver detalle de atencion", responses={200: AtencionServicioSerializer})
    def get(self, request, id_atencion):
        atencion = self._get_atencion(id_atencion, request)
        if not atencion:
            return Response({'error': 'Atencion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AtencionServicioSerializer(atencion).data)


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionAgregarServiciosView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Agregar servicios realizados durante la atencion",
        request=AtencionAgregarServiciosSerializer,
        responses={200: AtencionServicioSerializer}
    )
    def post(self, request, id_atencion):
        serializer = AtencionAgregarServiciosSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            atencion = agregar_servicios_atencion(id_atencion, serializer.validated_data['servicios'], getattr(request, 'usuario_actual', None))
            registrar_bitacora(request, 'AGREGAR_SERVICIOS_ATENCION', f'Servicios agregados a atencion: {atencion.id_atencion}.')
        except AtencionServicio.DoesNotExist:
            return Response({'error': 'Atencion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as error:
            return Response({'error': error.message_dict if hasattr(error, 'message_dict') else error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'mensaje': 'Servicios agregados correctamente.', 'atencion': AtencionServicioSerializer(atencion).data})


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionFinalizarView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Finalizar atencion",
        request=AtencionFinalizarSerializer,
        responses={200: AtencionServicioSerializer}
    )
    def post(self, request, id_atencion):
        serializer = AtencionFinalizarSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            atencion = finalizar_atencion(id_atencion, getattr(request, 'usuario_actual', None), serializer.validated_data.get('observaciones', ''))
            registrar_bitacora(request, 'FINALIZAR_ATENCION', f'Atencion finalizada: {atencion.id_atencion}.')
        except AtencionServicio.DoesNotExist:
            return Response({'error': 'Atencion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as error:
            return Response({'error': error.message_dict if hasattr(error, 'message_dict') else error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'mensaje': 'Atencion finalizada correctamente.', 'atencion': AtencionServicioSerializer(atencion).data})


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionNoAsistioView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Marcar atencion como no asistio",
        request=AtencionCambiarEstadoSerializer,
        responses={200: AtencionServicioSerializer}
    )
    def post(self, request, id_atencion):
        serializer = AtencionCambiarEstadoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            atencion = cambiar_estado_atencion(id_atencion, 'NO_ASISTIO', getattr(request, 'usuario_actual', None), serializer.validated_data.get('observaciones', ''))
            registrar_bitacora(request, 'ATENCION_NO_ASISTIO', f'Atencion marcada no asistio: {atencion.id_atencion}.')
        except AtencionServicio.DoesNotExist:
            return Response({'error': 'Atencion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as error:
            return Response({'error': error.message_dict if hasattr(error, 'message_dict') else error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'mensaje': 'Atencion marcada como no asistio.', 'atencion': AtencionServicioSerializer(atencion).data})


@extend_schema(tags=["CU23 - Registrar Atencion de Servicio"])
class AtencionCancelarView(APIView):
    permission_classes = [EsAdminOBarbero]

    @extend_schema(
        summary="Cancelar atencion",
        request=AtencionCambiarEstadoSerializer,
        responses={200: AtencionServicioSerializer}
    )
    def post(self, request, id_atencion):
        serializer = AtencionCambiarEstadoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            atencion = cambiar_estado_atencion(id_atencion, 'CANCELADA', getattr(request, 'usuario_actual', None), serializer.validated_data.get('observaciones', ''))
            registrar_bitacora(request, 'CANCELAR_ATENCION', f'Atencion cancelada: {atencion.id_atencion}.')
        except AtencionServicio.DoesNotExist:
            return Response({'error': 'Atencion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as error:
            return Response({'error': error.message_dict if hasattr(error, 'message_dict') else error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'mensaje': 'Atencion cancelada correctamente.', 'atencion': AtencionServicioSerializer(atencion).data})


# Consulta el historial de cambios de una cita.
# Sirve para defensa, auditoria y reportes.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class HistorialEstadoCitaListView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar historial de estados de una cita",
        responses={200: HistorialEstadoCitaSerializer(many=True), 404: OpenApiResponse(description="Cita no encontrada.")}
    )
    def get(self, request, id_cita):
        cita = Cita.objects.filter(pk=id_cita).first()
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        historial = cita.historial_estados.select_related('estado_anterior', 'estado_nuevo', 'cambiado_por').all()
        return Response(HistorialEstadoCitaSerializer(historial, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU12 - Gestionar Promociones"])
class PromocionListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar promociones",
        description="Lista promociones. Permite filtrar por estado, servicio y nombre.",
        responses={200: PromocionSerializer(many=True)}
    )
    def get(self, request):
        promociones = Promocion.consultar()
        estado_filtro = request.query_params.get('estado')
        id_servicio = request.query_params.get('id_servicio')
        nombre = request.query_params.get('nombre')

        if estado_filtro:
            promociones = promociones.filter(estado=estado_filtro.upper())
        if id_servicio:
            promociones = promociones.filter(servicios__id_servicio=id_servicio)
        if nombre:
            promociones = promociones.filter(nombre__icontains=nombre)

        registrar_bitacora(request, 'CONSULTAR_PROMOCIONES', 'Consulta de promociones.')
        return Response(PromocionSerializer(promociones.distinct(), many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear promocion",
        request=PromocionSerializer,
        responses={
            201: OpenApiResponse(description="Promocion registrada."),
            400: OpenApiResponse(description="Datos invalidos."),
        }
    )
    def post(self, request):
        serializer = PromocionSerializer(data=request.data)
        if serializer.is_valid():
            promocion = serializer.save()
            registrar_bitacora(request, 'CREAR_PROMOCION', f'Promocion creada: {promocion.id_promocion}.')
            return Response(
                {'mensaje': 'Promocion registrada correctamente.', 'promocion': PromocionSerializer(promocion).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU12 - Gestionar Promociones"])
class PromocionDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_promocion(self, id_promocion):
        try:
            return Promocion.consultar().get(pk=id_promocion)
        except Promocion.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de promocion",
        responses={200: PromocionSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_promocion):
        promocion = self._get_promocion(id_promocion)
        if not promocion:
            return Response({'error': 'Promocion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        registrar_bitacora(request, 'CONSULTAR_PROMOCIONES', f'Consulta de promocion {id_promocion}.')
        return Response(PromocionSerializer(promocion).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar promocion",
        request=PromocionSerializer,
        responses={
            200: OpenApiResponse(description="Promocion actualizada."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_promocion):
        promocion = self._get_promocion(id_promocion)
        if not promocion:
            return Response({'error': 'Promocion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        estado_anterior = promocion.estado
        serializer = PromocionSerializer(promocion, data=request.data, partial=True)
        if serializer.is_valid():
            promocion = serializer.save()
            if estado_anterior != 'ACTIVO' and promocion.estado == 'ACTIVO':
                try:
                    from apps.notificaciones.services import notificar_promocion_activada
                    notificar_promocion_activada(promocion)
                except Exception:
                    pass
            registrar_bitacora(request, 'ACTUALIZAR_PROMOCION', f'Promocion actualizada: {promocion.id_promocion}.')
            return Response(
                {'mensaje': 'Promocion actualizada correctamente.', 'promocion': PromocionSerializer(promocion).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar promocion",
        description="No elimina la promocion; la deja como INACTIVO.",
        responses={200: OpenApiResponse(description="Promocion desactivada."), 404: OpenApiResponse(description="No encontrada.")}
    )
    def delete(self, request, id_promocion):
        promocion = self._get_promocion(id_promocion)
        if not promocion:
            return Response({'error': 'Promocion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        promocion.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'DESACTIVAR_PROMOCION', f'Promocion desactivada: {promocion.id_promocion}.')
        return Response({'mensaje': 'Promocion desactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU26 - Gestionar Estaciones de Trabajo"])
class EstacionTrabajoListCreateView(APIView):
    # Solo el administrador puede registrar y consultar estaciones de trabajo.
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar estaciones de trabajo",
        description="Lista estaciones. Permite filtrar por estado, nombre y ubicacion interna.",
        responses={200: EstacionTrabajoSerializer(many=True)}
    )
    def get(self, request):
        # Lista estaciones registradas y permite filtrar la vista del frontend.
        estaciones = EstacionTrabajo.consultar()
        estado_filtro = request.query_params.get('estado')
        nombre = request.query_params.get('nombre')
        ubicacion_interna = request.query_params.get('ubicacion_interna')

        if estado_filtro:
            estaciones = estaciones.filter(estado=estado_filtro.upper())
        if nombre:
            estaciones = estaciones.filter(nombre__icontains=nombre)
        if ubicacion_interna:
            estaciones = estaciones.filter(ubicacion_interna__icontains=ubicacion_interna)

        registrar_bitacora(request, 'CONSULTAR_ESTACIONES_TRABAJO', 'Consulta de estaciones de trabajo.')
        return Response(EstacionTrabajoSerializer(estaciones, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Registrar estacion de trabajo",
        request=EstacionTrabajoSerializer,
        responses={
            201: OpenApiResponse(description="Estacion registrada."),
            400: OpenApiResponse(description="Datos invalidos o estacion duplicada."),
        },
        examples=[
            OpenApiExample(
                "Registrar estacion",
                value={
                    "nombre": "Estacion 1",
                    "descripcion": "Silla principal con espejo y herramientas basicas",
                    "ubicacion_interna": "Sala principal - lado izquierdo",
                    "estado": "ACTIVO",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Registra una nueva estacion si pasa las validaciones del serializer.
        serializer = EstacionTrabajoSerializer(data=request.data)
        if serializer.is_valid():
            estacion = serializer.save()
            registrar_bitacora(request, 'CREAR_ESTACION_TRABAJO', f'Estacion creada: {estacion.id_estacion}.')
            return Response(
                {
                    'mensaje': 'Estacion de trabajo registrada correctamente.',
                    'estacion': EstacionTrabajoSerializer(estacion).data,
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU26 - Gestionar Estaciones de Trabajo"])
class EstacionTrabajoDetalleView(APIView):
    # Maneja operaciones sobre una estacion especifica: ver, modificar o inactivar.
    permission_classes = [EsAdmin]

    def _get_estacion(self, id_estacion):
        # Busca la estacion por su llave primaria y devuelve None si no existe.
        try:
            return EstacionTrabajo.consultar().get(pk=id_estacion)
        except EstacionTrabajo.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de estacion de trabajo",
        responses={200: EstacionTrabajoSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_estacion):
        # Devuelve el detalle de una estacion para cargarlo en formularios o vistas.
        estacion = self._get_estacion(id_estacion)
        if not estacion:
            return Response({'error': 'Estacion de trabajo no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        registrar_bitacora(request, 'CONSULTAR_ESTACIONES_TRABAJO', f'Consulta de estacion {id_estacion}.')
        return Response(EstacionTrabajoSerializer(estacion).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar estacion de trabajo",
        request=EstacionTrabajoSerializer,
        responses={
            200: OpenApiResponse(description="Estacion actualizada."),
            400: OpenApiResponse(description="Datos invalidos o estacion duplicada."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_estacion):
        # Actualiza parcialmente la estacion; solo valida los campos enviados.
        estacion = self._get_estacion(id_estacion)
        if not estacion:
            return Response({'error': 'Estacion de trabajo no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = EstacionTrabajoSerializer(estacion, data=request.data, partial=True)
        if serializer.is_valid():
            estacion = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_ESTACION_TRABAJO', f'Estacion actualizada: {estacion.id_estacion}.')
            return Response(
                {
                    'mensaje': 'Estacion de trabajo actualizada correctamente.',
                    'estacion': EstacionTrabajoSerializer(estacion).data,
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Inactivar estacion de trabajo",
        description="No elimina la estacion; la deja como INACTIVO.",
        responses={
            200: OpenApiResponse(description="Estacion inactivada."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def delete(self, request, id_estacion):
        # Inactivacion logica: conserva el registro para auditoria y evita borrado fisico.
        estacion = self._get_estacion(id_estacion)
        if not estacion:
            return Response({'error': 'Estacion de trabajo no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        estacion.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'INACTIVAR_ESTACION_TRABAJO', f'Estacion inactivada: {estacion.id_estacion}.')
        return Response({'mensaje': 'Estacion de trabajo inactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU26 - Gestionar Estaciones de Trabajo"])
class EstacionTrabajoActivarView(APIView):
    # Endpoint separado para reactivar estaciones previamente inactivadas.
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Activar estacion de trabajo",
        responses={
            200: OpenApiResponse(description="Estacion activada."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def post(self, request, id_estacion):
        # Cambia el estado a ACTIVO y devuelve la estacion actualizada.
        estacion = EstacionTrabajo.objects.filter(pk=id_estacion).first()
        if not estacion:
            return Response({'error': 'Estacion de trabajo no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        estacion.cambiar_estado('ACTIVO')
        registrar_bitacora(request, 'ACTIVAR_ESTACION_TRABAJO', f'Estacion activada: {estacion.id_estacion}.')
        return Response(
            {
                'mensaje': 'Estacion de trabajo activada correctamente.',
                'estacion': EstacionTrabajoSerializer(estacion).data,
            },
            status=status.HTTP_200_OK
        )


@extend_schema(tags=["CU27 - Asignar Barbero a Estacion"])
class BarberosActivosEstacionView(APIView):
    # Endpoint de apoyo para el paso 2 del flujo: mostrar barberos activos/seleccionables.
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar barberos activos para asignacion",
        description="Si se envia fecha, excluye barberos con asistencia AUSENTE, PERMISO o INHABILITADO.",
        parameters=[OpenApiParameter(name='fecha', required=False, type=str)],
        responses={200: BarberoActivoSerializer(many=True)}
    )
    def get(self, request):
        # Base: todos los usuarios cuyo rol es Barbero.
        barberos = Usuario.objects.select_related('id_rol').filter(
            id_rol__nombre__iexact='barbero'
        ).order_by('nombre', 'apellido', 'codigo')

        # Si el frontend envia fecha, se quitan los barberos no disponibles por asistencia.
        fecha = parsear_fecha_frontend(request.query_params.get('fecha'))
        if fecha:
            barberos_no_disponibles = AsistenciaBarbero.objects.filter(
                fecha=fecha,
                estado__in=ESTADOS_ASISTENCIA_NO_DISPONIBLES,
            ).values_list('codigo_barbero_id', flat=True)
            barberos = barberos.exclude(codigo__in=barberos_no_disponibles)

        registrar_bitacora(request, 'CONSULTAR_BARBEROS_ASIGNACION_ESTACION', 'Consulta de barberos para asignacion de estacion.')
        return Response(BarberoActivoSerializer(barberos, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU27 - Asignar Barbero a Estacion"])
class EstacionesDisponiblesAsignacionView(APIView):
    # Endpoint de apoyo para el paso 4 del flujo: mostrar estaciones disponibles.
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar estaciones disponibles para asignacion",
        description="Con fecha, hora_inicio y hora_fin excluye estaciones ya ocupadas en ese rango.",
        parameters=[
            OpenApiParameter(name='fecha', required=False, type=str),
            OpenApiParameter(name='hora_inicio', required=False, type=str),
            OpenApiParameter(name='hora_fin', required=False, type=str),
        ],
        responses={200: EstacionTrabajoSerializer(many=True), 400: OpenApiResponse(description="Horario invalido.")}
    )
    def get(self, request):
        # Solo las estaciones ACTIVAS pueden aparecer como disponibles.
        estaciones = EstacionTrabajo.objects.filter(estado='ACTIVO')

        fecha = parsear_fecha_frontend(request.query_params.get('fecha'))
        hora_inicio = parsear_hora_frontend(request.query_params.get('hora_inicio'))
        hora_fin = parsear_hora_frontend(request.query_params.get('hora_fin'))

        # Si se consulta disponibilidad por turno, los tres datos son obligatorios.
        if any([request.query_params.get('fecha'), request.query_params.get('hora_inicio'), request.query_params.get('hora_fin')]):
            if not fecha or not hora_inicio or not hora_fin:
                return Response({'error': 'Debe enviar fecha, hora_inicio y hora_fin validos.'}, status=status.HTTP_400_BAD_REQUEST)
            if hora_inicio >= hora_fin:
                return Response({'error': 'La hora fin debe ser mayor a la hora inicio.'}, status=status.HTTP_400_BAD_REQUEST)

            # Busca estaciones ya ocupadas en un rango que cruza con el turno solicitado.
            estaciones_ocupadas = AsignacionEstacionTrabajo.objects.filter(
                fecha=fecha,
                estado='ACTIVO',
                hora_inicio__lt=hora_fin,
                hora_fin__gt=hora_inicio,
            ).values_list('id_estacion_id', flat=True)
            # La respuesta final excluye esas estaciones ocupadas.
            estaciones = estaciones.exclude(id_estacion__in=estaciones_ocupadas)

        registrar_bitacora(request, 'CONSULTAR_ESTACIONES_DISPONIBLES', 'Consulta de estaciones disponibles para asignacion.')
        return Response(EstacionTrabajoSerializer(estaciones, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU27 - Asignar Barbero a Estacion"])
class AsignacionEstacionTrabajoListCreateView(APIView):
    # CRUD principal de asignaciones: GET lista y POST registra una nueva asignacion.
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Listar asignaciones de estaciones",
        description="Permite filtrar por fecha, barbero, estacion y estado.",
        parameters=[
            OpenApiParameter(name='fecha', required=False, type=str),
            OpenApiParameter(name='codigo_barbero', required=False, type=str),
            OpenApiParameter(name='id_estacion', required=False, type=int),
            OpenApiParameter(name='estado', required=False, type=str),
        ],
        responses={200: AsignacionEstacionTrabajoSerializer(many=True)}
    )
    def get(self, request):
        # Lista las asignaciones registradas, con filtros para pantallas de consulta.
        asignaciones = AsignacionEstacionTrabajo.consultar().all()
        fecha = request.query_params.get('fecha')
        codigo_barbero = request.query_params.get('codigo_barbero')
        id_estacion = request.query_params.get('id_estacion')
        estado_filtro = request.query_params.get('estado')

        if fecha:
            asignaciones = asignaciones.filter(fecha=fecha)
        if codigo_barbero:
            asignaciones = asignaciones.filter(codigo_barbero_id=codigo_barbero)
        if id_estacion:
            asignaciones = asignaciones.filter(id_estacion_id=id_estacion)
        if estado_filtro:
            asignaciones = asignaciones.filter(estado=estado_filtro.upper())

        registrar_bitacora(request, 'CONSULTAR_ASIGNACIONES_ESTACION', 'Consulta de asignaciones de estacion.')
        return Response(AsignacionEstacionTrabajoSerializer(asignaciones, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Asignar barbero a estacion",
        request=AsignacionEstacionTrabajoSerializer,
        responses={
            201: OpenApiResponse(description="Asignacion registrada."),
            400: OpenApiResponse(description="Datos invalidos, barbero no disponible o estacion ocupada."),
        },
        examples=[
            OpenApiExample(
                "Asignar estacion",
                value={
                    "codigo_barbero": "BARB001",
                    "id_estacion": 1,
                    "fecha": "2026-07-05",
                    "hora_inicio": "09:00:00",
                    "hora_fin": "13:00:00",
                    "estado": "ACTIVO",
                    "observacion": "Turno de la manana",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Registra la asignacion usando el serializer, donde viven las reglas de negocio.
        serializer = AsignacionEstacionTrabajoSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            asignacion = serializer.save()
            registrar_bitacora(request, 'CREAR_ASIGNACION_ESTACION', f'Asignacion creada: {asignacion.id_asignacion}.')
            return Response(
                {
                    'mensaje': 'Barbero asignado a estacion correctamente.',
                    'asignacion': AsignacionEstacionTrabajoSerializer(asignacion).data,
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU27 - Asignar Barbero a Estacion"])
class AsignacionEstacionTrabajoDetalleView(APIView):
    # Operaciones sobre una asignacion concreta: ver, modificar o inactivar.
    permission_classes = [EsAdmin]

    def _get_asignacion(self, id_asignacion):
        # Busca con relaciones cargadas para responder el detalle completo.
        try:
            return AsignacionEstacionTrabajo.consultar().get(pk=id_asignacion)
        except AsignacionEstacionTrabajo.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de asignacion de estacion",
        responses={200: AsignacionEstacionTrabajoSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_asignacion):
        # Devuelve el detalle para que el frontend muestre o edite la asignacion.
        asignacion = self._get_asignacion(id_asignacion)
        if not asignacion:
            return Response({'error': 'Asignacion de estacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AsignacionEstacionTrabajoSerializer(asignacion).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar asignacion de estacion",
        request=AsignacionEstacionTrabajoSerializer,
        responses={
            200: OpenApiResponse(description="Asignacion actualizada."),
            400: OpenApiResponse(description="Datos invalidos o estacion ocupada."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_asignacion):
        # Actualiza parcialmente; si cambia horario, barbero, estacion o estado, se revalidan los cruces.
        asignacion = self._get_asignacion(id_asignacion)
        if not asignacion:
            return Response({'error': 'Asignacion de estacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AsignacionEstacionTrabajoSerializer(asignacion, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            asignacion = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_ASIGNACION_ESTACION', f'Asignacion actualizada: {asignacion.id_asignacion}.')
            return Response(
                {
                    'mensaje': 'Asignacion de estacion actualizada correctamente.',
                    'asignacion': AsignacionEstacionTrabajoSerializer(asignacion).data,
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Inactivar asignacion de estacion",
        description="No elimina la asignacion; la deja como INACTIVO.",
        responses={200: OpenApiResponse(description="Asignacion inactivada."), 404: OpenApiResponse(description="No encontrada.")}
    )
    def delete(self, request, id_asignacion):
        # Inactivacion logica: la asignacion deja de ocupar la estacion, pero queda registrada.
        asignacion = self._get_asignacion(id_asignacion)
        if not asignacion:
            return Response({'error': 'Asignacion de estacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        asignacion.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'INACTIVAR_ASIGNACION_ESTACION', f'Asignacion inactivada: {asignacion.id_asignacion}.')
        return Response({'mensaje': 'Asignacion de estacion inactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU27 - Asignar Barbero a Estacion"])
class AsignacionEstacionTrabajoActivarView(APIView):
    # Reactiva una asignacion validando nuevamente que no choque con otra asignacion activa.
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Activar asignacion de estacion",
        responses={
            200: OpenApiResponse(description="Asignacion activada."),
            400: OpenApiResponse(description="No se puede activar por reglas de negocio."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def post(self, request, id_asignacion):
        # Antes de activar, se pasa por el serializer para verificar que el turno siga libre.
        asignacion = AsignacionEstacionTrabajo.consultar().filter(pk=id_asignacion).first()
        if not asignacion:
            return Response({'error': 'Asignacion de estacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AsignacionEstacionTrabajoSerializer(
            asignacion,
            data={'estado': 'ACTIVO'},
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            asignacion = serializer.save()
            registrar_bitacora(request, 'ACTIVAR_ASIGNACION_ESTACION', f'Asignacion activada: {asignacion.id_asignacion}.')
            return Response(
                {
                    'mensaje': 'Asignacion de estacion activada correctamente.',
                    'asignacion': AsignacionEstacionTrabajoSerializer(asignacion).data,
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Endpoint de apoyo para frontend.
# Devuelve horarios disponibles segun barbero, servicio y fecha.
@extend_schema(tags=["CU24 - Consultar Disponibilidad"])
class DisponibilidadBarberoView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Consultar horarios disponibles",
        parameters=[
            OpenApiParameter(name='codigo_barbero', required=False, type=str),
            OpenApiParameter(name='id_servicio', required=False, type=int),
            OpenApiParameter(name='id_servicios', required=False, type=str),
            OpenApiParameter(name='fecha', required=True, type=str),
        ],
        responses={200: OpenApiResponse(description="Horarios disponibles.")}
    )
    def get(self, request):
        # Parametros obligatorios para calcular disponibilidad.
        codigo_barbero = obtener_query_param(
            request.query_params,
            'codigo_barbero',
            'codigoBarbero',
            'barbero',
            'id_barbero',
            'idBarbero',
        )
        id_servicio = obtener_query_param(
            request.query_params,
            'id_servicio',
            'idServicio',
            'servicio',
        )
        id_servicios = obtener_query_param(request.query_params, 'id_servicios', 'idServicios', 'servicios')
        fecha_valor = obtener_query_param(request.query_params, 'fecha', 'date')
        fecha = parsear_fecha_frontend(fecha_valor)

        if not (id_servicio or id_servicios) or not fecha:
            return Response(
                {
                    'error': 'Debe enviar id_servicio o id_servicios, y fecha. codigo_barbero es opcional.',
                    'recibido': {
                        'codigo_barbero': codigo_barbero,
                        'id_servicio': id_servicio,
                        'id_servicios': id_servicios,
                        'fecha': fecha_valor,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        ids_servicios = []
        if id_servicios:
            ids_servicios = [valor.strip() for valor in str(id_servicios).split(',') if valor.strip()]
        elif id_servicio:
            ids_servicios = [id_servicio]

        servicios = list(Servicio.objects.filter(pk__in=ids_servicios, estado='ACTIVO'))
        servicios_por_id = {str(servicio.pk): servicio for servicio in servicios}
        servicios = [servicios_por_id[str(id_item)] for id_item in ids_servicios if str(id_item) in servicios_por_id]

        if len(servicios) != len(ids_servicios):
            return Response({'error': 'Uno o mas servicios activos no fueron encontrados.'}, status=status.HTTP_404_NOT_FOUND)

        if es_modo_todos_barberos(codigo_barbero):
            barberos = Usuario.objects.select_related('id_rol').filter(
                id_rol__nombre__iexact='barbero'
            ).order_by('nombre', 'apellido', 'codigo')

            disponibilidad_por_barbero = []
            for barbero in barberos:
                resultado = calcular_disponibilidad_barbero(barbero, servicios, fecha)
                if resultado['disponibles']:
                    disponibilidad_por_barbero.append({
                        'codigo_barbero': barbero.codigo,
                        'barbero': f"{barbero.nombre} {barbero.apellido}".strip(),
                        'disponibles': resultado['disponibles'],
                    })

            mensaje = '' if disponibilidad_por_barbero else 'No hay horarios disponibles para la fecha y servicio seleccionados.'
            return Response(
                {
                    'fecha': fecha.isoformat(),
                    'servicios': [{'id_servicio': servicio.id_servicio, 'nombre': servicio.nombre, 'precio': servicio.precio} for servicio in servicios],
                    'duracion_total_minutos': sum(servicio.duracion_minutos for servicio in servicios),
                    'total_estimado': sum((servicio.precio for servicio in servicios), start=0),
                    'barberos': disponibilidad_por_barbero,
                    'mensaje': mensaje,
                },
                status=status.HTTP_200_OK
            )

        barbero = Usuario.objects.select_related('id_rol').filter(
            codigo=codigo_barbero,
            id_rol__nombre__iexact='barbero'
        ).first()
        if not barbero:
            return Response({'error': 'Barbero no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        resultado = calcular_disponibilidad_barbero(barbero, servicios, fecha)
        resultado.update({
            'servicios': [{'id_servicio': servicio.id_servicio, 'nombre': servicio.nombre, 'precio': servicio.precio} for servicio in servicios],
            'duracion_total_minutos': sum(servicio.duracion_minutos for servicio in servicios),
            'total_estimado': sum((servicio.precio for servicio in servicios), start=0),
        })
        return Response(resultado, status=status.HTTP_200_OK)
