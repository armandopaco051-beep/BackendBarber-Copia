from datetime import datetime, timedelta

from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.models import AsistenciaBarbero, BloqueoHorario, HorarioLaboral, Usuario
from apps.seguridad.permissions import EsAdmin
from apps.seguridad.views import registrar_bitacora
from apps.servicios.models import Servicio

from .models import BarberoServicio, Cita, EstadoCita
from .serializers import (
    BarberoServicioSerializer,
    CitaSerializer,
    DIAS_SEMANA,
    ESTADOS_NO_BLOQUEAN_HORARIO,
    EstadoCitaSerializer,
    HistorialEstadoCitaSerializer,
)


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


def cruza_intervalo(inicio_a, fin_a, inicio_b, fin_b):
    # Dos rangos se cruzan cuando el inicio de uno es menor al fin del otro y viceversa.
    return inicio_a < fin_b and fin_a > inicio_b


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
        ).all()

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
            ).get(pk=id_cita)
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


# Endpoint de apoyo para frontend.
# Devuelve horarios disponibles segun barbero, servicio y fecha.
@extend_schema(tags=["CU11 - Gestionar Citas"])
class DisponibilidadBarberoView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Consultar horarios disponibles",
        parameters=[
            OpenApiParameter(name='codigo_barbero', required=True, type=str),
            OpenApiParameter(name='id_servicio', required=True, type=int),
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
        fecha_valor = obtener_query_param(request.query_params, 'fecha', 'date')
        fecha = parsear_fecha_frontend(fecha_valor)

        if not codigo_barbero or not id_servicio or not fecha:
            return Response(
                {
                    'error': 'Debe enviar codigo_barbero, id_servicio y fecha.',
                    'recibido': {
                        'codigo_barbero': codigo_barbero,
                        'id_servicio': id_servicio,
                        'fecha': fecha_valor,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        barbero = Usuario.objects.select_related('id_rol').filter(codigo=codigo_barbero, id_rol__nombre__iexact='barbero').first()
        servicio = Servicio.objects.filter(pk=id_servicio, estado='ACTIVO').first()

        if not barbero:
            return Response({'error': 'Barbero no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        if not servicio:
            return Response({'error': 'Servicio activo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        if servicio.duracion_minutos <= 0:
            return Response(
                {'disponibles': [], 'mensaje': 'El servicio no tiene una duracion valida.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asistencia = AsistenciaBarbero.objects.filter(codigo_barbero=barbero, fecha=fecha).first()
        if asistencia and asistencia.estado in ['AUSENTE', 'PERMISO', 'INHABILITADO']:
            return Response({'disponibles': [], 'mensaje': 'El barbero no esta disponible por asistencia registrada.'})

        dia_semana = DIAS_SEMANA[fecha.weekday()]
        horarios = HorarioLaboral.objects.filter(
            codigo_barbero=barbero,
            dia_semana__iexact=dia_semana,
            estado__iexact='ACTIVO'
        )
        if not horarios.exists():
            horarios_registrados = HorarioLaboral.objects.filter(
                codigo_barbero=barbero
            ).values('dia_semana', 'hora_inicio', 'hora_fin', 'estado')
            return Response(
                {
                    'disponibles': [],
                    'mensaje': f'Barbero no disponible: no tiene horario laboral activo para {dia_semana}.',
                    'debug': {
                        'codigo_barbero': barbero.codigo,
                        'fecha': fecha.isoformat(),
                        'dia_semana_calculado': dia_semana,
                        'horarios_registrados': list(horarios_registrados),
                    }
                },
                status=status.HTTP_200_OK
            )

        disponibles = []

        bloqueos_del_dia = list(BloqueoHorario.objects.filter(
            codigo_barbero=barbero,
            fecha=fecha,
            estado__iexact='ACTIVO',
        ).values('hora_inicio', 'hora_fin'))

        citas_del_dia = list(Cita.objects.select_related('id_estadoc').filter(
            codigo_barbero=barbero,
            fecha=fecha,
        ).exclude(id_estadoc__nombre__in=ESTADOS_NO_BLOQUEAN_HORARIO).values('hora_inicio', 'hora_fin'))

        for horario in horarios:
            # Recorre la jornada laboral en bloques iguales a la duracion del servicio.
            inicio = datetime.combine(fecha, horario.hora_inicio)
            fin_jornada = datetime.combine(fecha, horario.hora_fin)
            paso = timedelta(minutes=servicio.duracion_minutos)

            while inicio + paso <= fin_jornada:
                hora_inicio = inicio.time()
                hora_fin = (inicio + paso).time()

                cruza_descanso = False
                if horario.hora_inicio_descanso and horario.hora_fin_descanso:
                    cruza_descanso = hora_inicio < horario.hora_fin_descanso and hora_fin > horario.hora_inicio_descanso

                cruza_bloqueo = any(
                    cruza_intervalo(hora_inicio, hora_fin, bloqueo['hora_inicio'], bloqueo['hora_fin'])
                    for bloqueo in bloqueos_del_dia
                )

                cruza_cita = any(
                    cruza_intervalo(hora_inicio, hora_fin, cita['hora_inicio'], cita['hora_fin'])
                    for cita in citas_del_dia
                )

                if not cruza_descanso and not cruza_bloqueo and not cruza_cita:
                    # Si no cruza descanso, bloqueo ni cita, se devuelve como disponible.
                    disponibles.append(hora_inicio.strftime('%H:%M:%S'))

                inicio += paso

        mensaje = ''
        if not disponibles:
            mensaje = 'No hay horarios disponibles para ese barbero, servicio y fecha.'

        return Response({'disponibles': disponibles, 'mensaje': mensaje}, status=status.HTTP_200_OK)
