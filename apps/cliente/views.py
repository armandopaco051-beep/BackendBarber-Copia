from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.citas.models import Cita
from apps.citas.serializers import CitaSerializer, ESTADOS_NO_BLOQUEAN_HORARIO
from apps.citas.views import DisponibilidadBarberoView
from apps.seguridad.views import registrar_bitacora

from .serializers import ClienteCitaSerializer


class EsCliente(BasePermission):
    # Permiso para endpoints propios del cliente autenticado.
    message = 'Solo clientes autenticados pueden acceder a esta accion.'

    def has_permission(self, request, view):
        usuario = getattr(request, 'usuario_actual', None)
        return bool(usuario and usuario.es_cliente)


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
