from django.utils import timezone
from django.db.models import Sum
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.citas.models import AtencionServicio, Cita, DetalleAtencionServicio
from apps.citas.serializers import CitaSerializer, ESTADOS_NO_BLOQUEAN_HORARIO
from apps.citas.views import DisponibilidadBarberoView
from apps.seguridad.permissions import EsAdmin
from apps.seguridad.views import registrar_bitacora
from apps.servicios.models import RecomendacionCuidado
from apps.servicios.serializers import RecomendacionCuidadoSerializer
from apps.ventas_caja.models import CampaniaFidelizacion, Venta

from .models import EncuestaSatisfaccion, ReclamoSugerencia
from .serializers import (
    ClienteCitaSerializer,
    EncuestaSatisfaccionSerializer,
    ReclamoSugerenciaSerializer,
    RespuestaReclamoSugerenciaSerializer,
    RespuestaEncuestaSatisfaccionSerializer,
)


class EsCliente(BasePermission):
    # Permiso para endpoints propios del cliente autenticado.
    message = 'Solo clientes autenticados pueden acceder a esta accion.'

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        return bool(usuario and usuario.es_cliente)


class EsClienteOAdmin(BasePermission):
    # Permite registrar al cliente y hacer seguimiento al administrador.
    message = 'Solo clientes o administradores autenticados pueden acceder.'

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        return bool(usuario and (usuario.es_cliente or usuario.es_admin))


def obtener_cliente_actual(request):
    return getattr(request, 'usuario_actual', None)


def queryset_citas_cliente(cliente):
    # Base query para que el cliente solo vea sus propias citas.
    return Cita.objects.select_related(
        'codigo_cliente',
        'codigo_cliente__id_rol',
        'codigo_barbero',
        'codigo_barbero__id_rol',
        'id_servicio',
        'id_estadoc',
        'registrado_por',
    ).filter(codigo_cliente=cliente)


@extend_schema(tags=['Cliente - Dashboard'])
class ClienteDashboardView(APIView):
    permission_classes = [EsCliente]

    @extend_schema(
        summary='Dashboard del cliente',
        description='Devuelve resumen de citas del cliente autenticado.',
        responses={200: OpenApiResponse(description='Resumen del cliente.')}
    )
    def get(self, request):
        cliente = obtener_cliente_actual(request)
        hoy = timezone.localdate()
        citas = queryset_citas_cliente(cliente)

        proxima_cita = citas.exclude(
            id_estadoc__nombre__in=['CANCELADA', 'ANULADA', 'FINALIZADA', 'NO_ASISTIO']
        ).filter(fecha__gte=hoy).order_by('fecha', 'hora_inicio').first()

        data = {
            'cliente': {
                'codigo': cliente.codigo,
                'nombre': cliente.nombre,
                'apellido': cliente.apellido,
                'correo': cliente.correo,
            },
            'proxima_cita': CitaSerializer(proxima_cita).data if proxima_cita else None,
            'total_citas': citas.count(),
            'citas_pendientes': citas.filter(id_estadoc__nombre__in=['PENDIENTE', 'CONFIRMADA', 'REPROGRAMADA']).count(),
        }
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(tags=['Cliente - Reservas'])
class ClienteDisponibilidadView(DisponibilidadBarberoView):
    # Misma logica de disponibilidad de admin, pero accesible para cliente autenticado.
    permission_classes = [EsCliente]


@extend_schema(tags=['Cliente - Mis Citas'])
class ClienteCitaListCreateView(APIView):
    permission_classes = [EsCliente]

    @extend_schema(
        summary='Listar mis citas',
        description='Lista solo las citas del cliente autenticado.',
        responses={200: CitaSerializer(many=True)}
    )
    def get(self, request):
        cliente = obtener_cliente_actual(request)
        citas = queryset_citas_cliente(cliente)

        fecha = request.query_params.get('fecha')
        estado_filtro = request.query_params.get('estado')

        if fecha:
            citas = citas.filter(fecha=fecha)
        if estado_filtro:
            citas = citas.filter(id_estadoc__nombre=estado_filtro.upper().replace(' ', '_'))

        registrar_bitacora(request, 'CLIENTE_CONSULTAR_CITAS', f'Cliente consulto sus citas: {cliente.codigo}.', cliente)
        return Response(CitaSerializer(citas, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Reservar cita como cliente',
        description='Crea una cita usando el cliente autenticado como codigo_cliente.',
        request=ClienteCitaSerializer,
        responses={
            201: OpenApiResponse(description='Cita reservada.'),
            400: OpenApiResponse(description='Datos invalidos o horario no disponible.'),
        },
        examples=[
            OpenApiExample(
                'Reservar cita',
                value={
                    'codigo_barbero': '441236',
                    'id_servicio': 2,
                    'fecha': '2026-05-12',
                    'hora_inicio': '09:15:00',
                    'observacion': 'Quiero mid fade',
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        cliente = obtener_cliente_actual(request)
        data = request.data.copy()
        data.setdefault('estado', 'PENDIENTE')
        serializer = ClienteCitaSerializer(data=data, context={'request': request, 'cliente': cliente})
        if serializer.is_valid():
            cita = serializer.save()
            registrar_bitacora(request, 'CLIENTE_CREAR_CITA', f'Cliente reservo cita: {cita.id_cita}.', cliente)
            return Response(
                {'mensaje': 'Cita reservada correctamente.', 'cita': CitaSerializer(cita).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Cliente - Mis Citas'])
class ClienteCitaDetalleView(APIView):
    permission_classes = [EsCliente]

    def _get_cita_cliente(self, request, id_cita):
        cliente = obtener_cliente_actual(request)
        return queryset_citas_cliente(cliente).filter(pk=id_cita).first()

    @extend_schema(
        summary='Ver detalle de mi cita',
        responses={200: CitaSerializer, 404: OpenApiResponse(description='Cita no encontrada.')}
    )
    def get(self, request, id_cita):
        cita = self._get_cita_cliente(request, id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CitaSerializer(cita).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Reprogramar mi cita',
        description='Permite cambiar servicio, barbero, fecha, hora u observacion de una cita propia.',
        request=ClienteCitaSerializer,
        responses={
            200: OpenApiResponse(description='Cita reprogramada.'),
            400: OpenApiResponse(description='Datos invalidos o horario no disponible.'),
            404: OpenApiResponse(description='Cita no encontrada.'),
        }
    )
    def put(self, request, id_cita):
        cliente = obtener_cliente_actual(request)
        cita = self._get_cita_cliente(request, id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        if cita.id_estadoc.nombre in ['FINALIZADA', 'CANCELADA', 'ANULADA', 'NO_ASISTIO']:
            return Response({'error': 'Esta cita ya no puede reprogramarse.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        data['estado'] = 'REPROGRAMADA'
        serializer = ClienteCitaSerializer(cita, data=data, partial=True, context={'request': request, 'cliente': cliente})
        if serializer.is_valid():
            cita = serializer.save()
            registrar_bitacora(request, 'CLIENTE_REPROGRAMAR_CITA', f'Cliente reprogramo cita: {cita.id_cita}.', cliente)
            return Response(
                {'mensaje': 'Cita reprogramada correctamente.', 'cita': CitaSerializer(cita).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary='Cancelar mi cita',
        description='No elimina fisicamente; cambia el estado a CANCELADA.',
        responses={
            200: OpenApiResponse(description='Cita cancelada.'),
            404: OpenApiResponse(description='Cita no encontrada.'),
        }
    )
    def delete(self, request, id_cita):
        cliente = obtener_cliente_actual(request)
        cita = self._get_cita_cliente(request, id_cita)
        if not cita:
            return Response({'error': 'Cita no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        if cita.id_estadoc.nombre in ['FINALIZADA', 'CANCELADA', 'ANULADA', 'NO_ASISTIO']:
            return Response({'error': 'Esta cita ya no puede cancelarse.'}, status=status.HTTP_400_BAD_REQUEST)

        motivo = request.data.get('motivo_cancelacion', 'Cancelada por el cliente') if hasattr(request, 'data') else 'Cancelada por el cliente'
        serializer = ClienteCitaSerializer(
            cita,
            data={'estado': 'CANCELADA', 'motivo_cancelacion': motivo},
            partial=True,
            context={'request': request, 'cliente': cliente}
        )
        if serializer.is_valid():
            serializer.save()
            registrar_bitacora(request, 'CLIENTE_CANCELAR_CITA', f'Cliente cancelo cita: {cita.id_cita}.', cliente)
            return Response({'mensaje': 'Cita cancelada correctamente.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Cliente - Recomendaciones'])
class ClienteRecomendacionListView(APIView):
    permission_classes = [EsCliente]

    @extend_schema(
        summary='Consultar recomendaciones recibidas',
        description='Lista recomendaciones de cuidado registradas por barberos para el cliente autenticado.',
        responses={200: RecomendacionCuidadoSerializer(many=True)}
    )
    def get(self, request):
        cliente = obtener_cliente_actual(request)
        recomendaciones = RecomendacionCuidado.consultar().filter(codigo_cliente=cliente, estado='ACTIVO')
        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        id_servicio = request.query_params.get('id_servicio')

        if fecha_desde:
            recomendaciones = recomendaciones.filter(id_atencion__fecha__gte=fecha_desde)
        if fecha_hasta:
            recomendaciones = recomendaciones.filter(id_atencion__fecha__lte=fecha_hasta)
        if id_servicio:
            recomendaciones = recomendaciones.filter(id_atencion__id_cita__id_servicio_id=id_servicio)

        registrar_bitacora(request, 'CONSULTAR_RECOMENDACIONES_CLIENTE', 'Cliente consulta recomendaciones recibidas.')
        return Response(
            {
                'mensaje': 'No existen recomendaciones registradas.' if not recomendaciones.exists() else 'Recomendaciones consultadas correctamente.',
                'recomendaciones': RecomendacionCuidadoSerializer(recomendaciones, many=True).data,
            },
            status=status.HTTP_200_OK
        )


@extend_schema(tags=['Cliente - Fidelizacion'])
class ClienteBeneficioFidelizacionView(APIView):
    permission_classes = [EsCliente]

    def _metricas_cliente(self, cliente):
        atenciones_finalizadas = AtencionServicio.objects.filter(codigo_cliente=cliente, estado='FINALIZADA')
        ventas_pagadas = Venta.objects.filter(codigo_cliente=cliente, estado='PAGADA')
        servicios_acumulados = DetalleAtencionServicio.objects.filter(
            id_atencion__codigo_cliente=cliente,
            id_atencion__estado='FINALIZADA',
        ).aggregate(total=Sum('cantidad'))['total'] or 0

        return {
            'visitas': atenciones_finalizadas.count(),
            'servicios': servicios_acumulados,
            'monto': ventas_pagadas.aggregate(total=Sum('total'))['total'] or 0,
        }

    def _avance_campania(self, campania, metricas):
        acumulado = metricas.get(campania.tipo_condicion.lower(), 0)
        requerido = campania.valor_condicion
        faltante = max(requerido - acumulado, 0)
        return {
            'id_campania': campania.id_campania,
            'nombre': campania.nombre,
            'descripcion': campania.descripcion,
            'tipo_condicion': campania.tipo_condicion,
            'valor_condicion': requerido,
            'acumulado_cliente': acumulado,
            'faltante': faltante,
            'beneficio_disponible': acumulado >= requerido,
            'tipo_beneficio': campania.tipo_beneficio,
            'valor_beneficio': campania.valor_beneficio,
            'beneficio': campania.beneficio,
            'fecha_inicio': campania.fecha_inicio,
            'fecha_fin': campania.fecha_fin,
        }

    @extend_schema(
        summary='Consultar beneficios de fidelizacion',
        description='Calcula visitas, servicios o monto acumulado del cliente contra campanias activas.',
        responses={200: OpenApiResponse(description='Beneficios y avance de fidelizacion.')}
    )
    def get(self, request):
        cliente = obtener_cliente_actual(request)
        hoy = timezone.localdate()
        campanias = CampaniaFidelizacion.consultar().filter(
            estado='ACTIVA',
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
        )
        if not campanias.exists():
            return Response({'mensaje': 'No existen campanias activas.', 'beneficios': []}, status=status.HTTP_200_OK)

        metricas = self._metricas_cliente(cliente)
        if not any(metricas.values()):
            return Response(
                {'mensaje': 'Cliente sin historial.', 'metricas': metricas, 'beneficios': []},
                status=status.HTTP_200_OK
            )

        beneficios = [self._avance_campania(campania, metricas) for campania in campanias]
        registrar_bitacora(request, 'CONSULTAR_BENEFICIOS_FIDELIZACION', 'Cliente consulta beneficios de fidelizacion.')
        return Response(
            {
                'mensaje': 'Beneficios de fidelizacion consultados correctamente.',
                'metricas': metricas,
                'beneficios': beneficios,
            },
            status=status.HTTP_200_OK
        )


@extend_schema(tags=['Cliente - Encuestas'])
class ClienteResponderEncuestaView(APIView):
    permission_classes = [EsCliente]

    @extend_schema(
        summary='Responder encuesta de satisfaccion',
        request=RespuestaEncuestaSatisfaccionSerializer,
        responses={
            201: OpenApiResponse(description='Encuesta respondida.'),
            400: OpenApiResponse(description='Encuesta ya respondida, inactiva o respuestas incompletas.'),
        },
        examples=[
            OpenApiExample(
                'Responder encuesta',
                value={
                    'id_encuesta': 1,
                    'id_atencion': 1,
                    'respuestas': [
                        {'id_pregunta': 1, 'id_opcion': 5},
                        {'id_pregunta': 2, 'respuesta_texto': 'Muy buena atencion.'},
                    ],
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = RespuestaEncuestaSatisfaccionSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            respuesta = serializer.save()
            registrar_bitacora(request, 'RESPONDER_ENCUESTA_SATISFACCION', f'Encuesta respondida: {respuesta.id_respuesta}.')
            return Response(
                {
                    'mensaje': 'Encuesta respondida correctamente.',
                    'respuesta': RespuestaEncuestaSatisfaccionSerializer(respuesta).data,
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# CRUD de CU30 Gestionar encuesta de satisfaccion.
# El administrador crea encuestas con preguntas y opciones para clientes atendidos.
@extend_schema(tags=['CU30 - Gestionar Encuestas de Satisfaccion'])
class EncuestaSatisfaccionListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary='Listar encuestas de satisfaccion',
        description='Lista encuestas. Permite filtrar por estado y titulo.',
        responses={200: EncuestaSatisfaccionSerializer(many=True)}
    )
    def get(self, request):
        # Muestra las encuestas registradas en el modulo administrativo.
        encuestas = EncuestaSatisfaccion.consultar().all()
        estado_filtro = request.query_params.get('estado')
        titulo = request.query_params.get('titulo')

        if estado_filtro:
            encuestas = encuestas.filter(estado=estado_filtro.upper())
        if titulo:
            encuestas = encuestas.filter(titulo__icontains=titulo)

        registrar_bitacora(request, 'CONSULTAR_ENCUESTAS_SATISFACCION', 'Consulta de encuestas de satisfaccion.')
        return Response(EncuestaSatisfaccionSerializer(encuestas, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Crear encuesta de satisfaccion',
        request=EncuestaSatisfaccionSerializer,
        responses={
            201: OpenApiResponse(description='Encuesta registrada.'),
            400: OpenApiResponse(description='Datos invalidos.'),
        },
        examples=[
            OpenApiExample(
                'Crear encuesta',
                value={
                    'titulo': 'Encuesta post atencion',
                    'descripcion': 'Evalua puntualidad, limpieza y experiencia.',
                    'estado': 'BORRADOR',
                    'preguntas': [
                        {
                            'texto': 'Como calificas la puntualidad?',
                            'tipo_respuesta': 'ESCALA',
                            'orden': 1,
                            'obligatoria': True,
                            'opciones': [
                                {'texto': '1', 'valor': 1, 'orden': 1},
                                {'texto': '2', 'valor': 2, 'orden': 2},
                                {'texto': '3', 'valor': 3, 'orden': 3},
                                {'texto': '4', 'valor': 4, 'orden': 4},
                                {'texto': '5', 'valor': 5, 'orden': 5},
                            ],
                        }
                    ],
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Guarda la encuesta completa con sus preguntas y opciones.
        serializer = EncuestaSatisfaccionSerializer(data=request.data)
        if serializer.is_valid():
            encuesta = serializer.save()
            registrar_bitacora(request, 'CREAR_ENCUESTA_SATISFACCION', f'Encuesta creada: {encuesta.id_encuesta}.')
            return Response(
                {'mensaje': 'Encuesta de satisfaccion registrada correctamente.', 'encuesta': EncuestaSatisfaccionSerializer(encuesta).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['CU30 - Gestionar Encuestas de Satisfaccion'])
class EncuestaSatisfaccionDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_encuesta(self, id_encuesta):
        # Obtiene la encuesta con preguntas y opciones para detalle o edicion.
        return EncuestaSatisfaccion.consultar().filter(pk=id_encuesta).first()

    @extend_schema(
        summary='Ver detalle de encuesta de satisfaccion',
        responses={200: EncuestaSatisfaccionSerializer, 404: OpenApiResponse(description='No encontrada.')}
    )
    def get(self, request, id_encuesta):
        encuesta = self._get_encuesta(id_encuesta)
        if not encuesta:
            return Response({'error': 'Encuesta de satisfaccion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(EncuestaSatisfaccionSerializer(encuesta).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Actualizar encuesta de satisfaccion',
        request=EncuestaSatisfaccionSerializer,
        responses={
            200: OpenApiResponse(description='Encuesta actualizada.'),
            400: OpenApiResponse(description='Datos invalidos.'),
            404: OpenApiResponse(description='No encontrada.'),
        }
    )
    def put(self, request, id_encuesta):
        # Actualiza datos generales y, si se envian preguntas, reemplaza su estructura completa.
        encuesta = self._get_encuesta(id_encuesta)
        if not encuesta:
            return Response({'error': 'Encuesta de satisfaccion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = EncuestaSatisfaccionSerializer(encuesta, data=request.data, partial=True)
        if serializer.is_valid():
            encuesta = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_ENCUESTA_SATISFACCION', f'Encuesta actualizada: {encuesta.id_encuesta}.')
            return Response(
                {'mensaje': 'Encuesta de satisfaccion actualizada correctamente.', 'encuesta': EncuestaSatisfaccionSerializer(encuesta).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary='Inactivar encuesta de satisfaccion',
        description='No elimina la encuesta; la deja como INACTIVO.',
        responses={200: OpenApiResponse(description='Encuesta inactivada.'), 404: OpenApiResponse(description='No encontrada.')}
    )
    def delete(self, request, id_encuesta):
        # Retira la encuesta para que deje de estar disponible a clientes atendidos.
        encuesta = self._get_encuesta(id_encuesta)
        if not encuesta:
            return Response({'error': 'Encuesta de satisfaccion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        encuesta.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'INACTIVAR_ENCUESTA_SATISFACCION', f'Encuesta inactivada: {encuesta.id_encuesta}.')
        return Response({'mensaje': 'Encuesta de satisfaccion inactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=['CU30 - Gestionar Encuestas de Satisfaccion'])
class EncuestaSatisfaccionActivarView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary='Activar encuesta de satisfaccion',
        responses={200: OpenApiResponse(description='Encuesta activada.'), 404: OpenApiResponse(description='No encontrada.')}
    )
    def post(self, request, id_encuesta):
        # Publica la encuesta para clientes atendidos.
        encuesta = EncuestaSatisfaccion.consultar().filter(pk=id_encuesta).first()
        if not encuesta:
            return Response({'error': 'Encuesta de satisfaccion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        encuesta.cambiar_estado('ACTIVO')
        registrar_bitacora(request, 'ACTIVAR_ENCUESTA_SATISFACCION', f'Encuesta activada: {encuesta.id_encuesta}.')
        return Response(
            {'mensaje': 'Encuesta de satisfaccion activada correctamente.', 'encuesta': EncuestaSatisfaccionSerializer(encuesta).data},
            status=status.HTTP_200_OK
        )


# CRUD de CU31 Gestionar reclamos y sugerencias.
# Cliente registra solicitudes; administrador consulta y actualiza seguimiento.
@extend_schema(tags=['CU31 - Gestionar Reclamos y Sugerencias'])
class ReclamoSugerenciaListCreateView(APIView):
    permission_classes = [EsClienteOAdmin]

    def _filtrar_por_usuario(self, queryset, request):
        # Admin ve todas las solicitudes; cliente solo las propias.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario:
            return queryset.none()
        if usuario.es_admin:
            return queryset
        return queryset.filter(codigo_cliente=usuario)

    @extend_schema(
        summary='Listar reclamos y sugerencias',
        description='Cliente ve sus solicitudes; administrador ve todas y puede filtrar.',
        responses={200: ReclamoSugerenciaSerializer(many=True)}
    )
    def get(self, request):
        solicitudes = self._filtrar_por_usuario(ReclamoSugerencia.consultar().all(), request)
        tipo = request.query_params.get('tipo_solicitud')
        estado_filtro = request.query_params.get('estado')
        codigo_cliente = request.query_params.get('codigo_cliente')
        id_cita = request.query_params.get('id_cita')
        id_servicio = request.query_params.get('id_servicio')

        if tipo:
            solicitudes = solicitudes.filter(tipo_solicitud=tipo.upper())
        if estado_filtro:
            solicitudes = solicitudes.filter(estado=estado_filtro.upper())
        if codigo_cliente:
            solicitudes = solicitudes.filter(codigo_cliente_id=codigo_cliente)
        if id_cita:
            solicitudes = solicitudes.filter(id_cita_id=id_cita)
        if id_servicio:
            solicitudes = solicitudes.filter(id_servicio_id=id_servicio)

        registrar_bitacora(request, 'CONSULTAR_RECLAMOS_SUGERENCIAS', 'Consulta de reclamos y sugerencias.')
        return Response(ReclamoSugerenciaSerializer(solicitudes, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Registrar reclamo o sugerencia',
        request=ReclamoSugerenciaSerializer,
        responses={
            201: OpenApiResponse(description='Solicitud registrada.'),
            400: OpenApiResponse(description='Datos invalidos.'),
            403: OpenApiResponse(description='Usuario sin permiso.'),
        },
        examples=[
            OpenApiExample(
                'Registrar reclamo',
                value={
                    'tipo_solicitud': 'RECLAMO',
                    'detalle': 'La atencion inicio con retraso.',
                    'id_cita': 1,
                    'id_servicio': 2,
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Solo clientes pueden registrar solicitudes desde este caso de uso.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or not usuario.es_cliente:
            return Response({'error': 'Solo clientes autenticados pueden registrar reclamos o sugerencias.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReclamoSugerenciaSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            solicitud = serializer.save()
            registrar_bitacora(request, 'CREAR_RECLAMO_SUGERENCIA', f'Solicitud registrada: {solicitud.id_solicitud}.', usuario)
            return Response(
                {
                    'mensaje': 'Reclamo o sugerencia registrado correctamente.',
                    'solicitud': ReclamoSugerenciaSerializer(solicitud).data,
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['CU31 - Gestionar Reclamos y Sugerencias'])
class ReclamoSugerenciaDetalleView(APIView):
    permission_classes = [EsClienteOAdmin]

    def _get_solicitud(self, request, id_solicitud):
        # Aplica visibilidad por rol al consultar el detalle.
        usuario = getattr(request, 'usuario_actual', None)
        queryset = ReclamoSugerencia.consultar()
        if not usuario:
            return None
        if usuario.es_cliente:
            queryset = queryset.filter(codigo_cliente=usuario)
        elif not usuario.es_admin:
            return None
        return queryset.filter(pk=id_solicitud).first()

    @extend_schema(
        summary='Ver detalle de reclamo o sugerencia',
        responses={200: ReclamoSugerenciaSerializer, 404: OpenApiResponse(description='No encontrada.')}
    )
    def get(self, request, id_solicitud):
        solicitud = self._get_solicitud(request, id_solicitud)
        if not solicitud:
            return Response({'error': 'Solicitud no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReclamoSugerenciaSerializer(solicitud).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Actualizar seguimiento de reclamo o sugerencia',
        description='El administrador puede cambiar estado, respuesta y datos relacionados.',
        request=ReclamoSugerenciaSerializer,
        responses={
            200: OpenApiResponse(description='Solicitud actualizada.'),
            400: OpenApiResponse(description='Datos invalidos.'),
            403: OpenApiResponse(description='Usuario sin permiso.'),
            404: OpenApiResponse(description='No encontrada.'),
        }
    )
    def put(self, request, id_solicitud):
        # Solo administrador hace seguimiento formal de la solicitud.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or not usuario.es_admin:
            return Response({'error': 'Solo el administrador puede actualizar solicitudes.'}, status=status.HTTP_403_FORBIDDEN)

        solicitud = self._get_solicitud(request, id_solicitud)
        if not solicitud:
            return Response({'error': 'Solicitud no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReclamoSugerenciaSerializer(solicitud, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            solicitud = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_RECLAMO_SUGERENCIA', f'Solicitud actualizada: {solicitud.id_solicitud}.')
            return Response(
                {
                    'mensaje': 'Solicitud actualizada correctamente.',
                    'solicitud': ReclamoSugerenciaSerializer(solicitud).data,
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary='Inactivar reclamo o sugerencia',
        description='No elimina la solicitud; cambia su estado a INACTIVO.',
        responses={
            200: OpenApiResponse(description='Solicitud inactivada.'),
            403: OpenApiResponse(description='Usuario sin permiso.'),
            404: OpenApiResponse(description='No encontrada.'),
        }
    )
    def delete(self, request, id_solicitud):
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or not usuario.es_admin:
            return Response({'error': 'Solo el administrador puede inactivar solicitudes.'}, status=status.HTTP_403_FORBIDDEN)

        solicitud = self._get_solicitud(request, id_solicitud)
        if not solicitud:
            return Response({'error': 'Solicitud no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        solicitud.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'INACTIVAR_RECLAMO_SUGERENCIA', f'Solicitud inactivada: {solicitud.id_solicitud}.')
        return Response({'mensaje': 'Solicitud inactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=['CU32 - Gestionar Respuesta a Reclamos'])
class RespuestaReclamoSugerenciaView(APIView):
    permission_classes = [EsAdmin]

    def _get_solicitud(self, id_solicitud):
        # El administrador puede responder cualquier solicitud registrada.
        return ReclamoSugerencia.consultar().filter(pk=id_solicitud).first()

    @extend_schema(
        summary='Responder reclamo o sugerencia',
        description='Registra la respuesta o accion tomada y cambia el estado a revisado, resuelto u otro estado de seguimiento.',
        request=RespuestaReclamoSugerenciaSerializer,
        responses={
            200: OpenApiResponse(description='Solicitud respondida.'),
            400: OpenApiResponse(description='Respuesta vacia o estado invalido.'),
            404: OpenApiResponse(description='Solicitud inexistente.'),
        },
        examples=[
            OpenApiExample(
                'Responder solicitud',
                value={
                    'respuesta_admin': 'Se contacto al cliente y se ofrecio una nueva atencion sin costo.',
                    'estado': 'RESUELTO',
                },
                request_only=True,
            )
        ]
    )
    def post(self, request, id_solicitud):
        # Flujo CU32: revisar detalle, registrar respuesta y actualizar estado.
        solicitud = self._get_solicitud(id_solicitud)
        if not solicitud:
            return Response({'error': 'Solicitud no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = RespuestaReclamoSugerenciaSerializer(solicitud, data=request.data)
        if serializer.is_valid():
            solicitud = serializer.save()
            registrar_bitacora(request, 'RESPONDER_RECLAMO_SUGERENCIA', f'Solicitud respondida: {solicitud.id_solicitud}.')
            return Response(
                {
                    'mensaje': 'Respuesta registrada correctamente.',
                    'solicitud': ReclamoSugerenciaSerializer(solicitud).data,
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
