from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.permissions import EsAdmin, EsAdminOCajero
from apps.seguridad.views import registrar_bitacora

from .models import Caja, MetodoPago, PlanComision
from .serializers import (
    CajaAperturaSerializer,
    CajaCierreSerializer,
    CajaSerializer,
    MetodoPagoSerializer,
    PlanComisionSerializer,
)


def accion_estado(estado, accion_activar, accion_actualizar):
    return accion_activar if estado == 'ACTIVO' else accion_actualizar


@extend_schema(tags=["CU13 - Gestionar Metodos de Pago"])
class MetodoPagoListCreateView(APIView):
    permission_classes = [EsAdmin]
    serializer_class = MetodoPagoSerializer

    @extend_schema(
        summary="Listar metodos de pago",
        responses={200: MetodoPagoSerializer(many=True)}
    )
    def get(self, request):
        metodos = MetodoPago.consultar()
        estado_filtro = request.query_params.get('estado')
        nombre = request.query_params.get('nombre')

        if estado_filtro:
            metodos = metodos.filter(estado=estado_filtro.upper())
        if nombre:
            metodos = metodos.filter(nombre__icontains=nombre)

        registrar_bitacora(request, 'CONSULTAR_METODOS_PAGO', 'Consulta de metodos de pago.')
        return Response(MetodoPagoSerializer(metodos, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear metodo de pago",
        request=MetodoPagoSerializer,
        responses={
            201: OpenApiResponse(description="Metodo de pago registrado."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Crear metodo de pago",
                value={
                    "nombre": "QR",
                    "descripcion": "Pago por codigo QR",
                    "requiere_referencia": True,
                    "estado": "ACTIVO",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = MetodoPagoSerializer(data=request.data)
        if serializer.is_valid():
            metodo = serializer.save()
            registrar_bitacora(request, 'CREAR_METODO_PAGO', f'Metodo de pago creado: {metodo.id_metodo_pago}.')
            return Response(
                {'mensaje': 'Metodo de pago registrado correctamente.', 'metodo_pago': MetodoPagoSerializer(metodo).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU13 - Gestionar Metodos de Pago"])
class MetodoPagoDetalleView(APIView):
    permission_classes = [EsAdmin]
    serializer_class = MetodoPagoSerializer

    def _get_metodo(self, id_metodo_pago):
        try:
            return MetodoPago.objects.get(pk=id_metodo_pago)
        except MetodoPago.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de metodo de pago",
        responses={200: MetodoPagoSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, id_metodo_pago):
        metodo = self._get_metodo(id_metodo_pago)
        if not metodo:
            return Response({'error': 'Metodo de pago no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(MetodoPagoSerializer(metodo).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar metodo de pago",
        request=MetodoPagoSerializer,
        responses={
            200: OpenApiResponse(description="Metodo de pago actualizado."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def put(self, request, id_metodo_pago):
        metodo = self._get_metodo(id_metodo_pago)
        if not metodo:
            return Response({'error': 'Metodo de pago no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        estado_anterior = metodo.estado
        serializer = MetodoPagoSerializer(metodo, data=request.data, partial=True)
        if serializer.is_valid():
            metodo = serializer.save()
            accion = accion_estado(metodo.estado, 'ACTIVAR_METODO_PAGO', 'ACTUALIZAR_METODO_PAGO') if estado_anterior != metodo.estado else 'ACTUALIZAR_METODO_PAGO'
            registrar_bitacora(request, accion, f'Metodo de pago actualizado: {metodo.id_metodo_pago}.')
            return Response(
                {'mensaje': 'Metodo de pago actualizado correctamente.', 'metodo_pago': MetodoPagoSerializer(metodo).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar metodo de pago",
        responses={200: OpenApiResponse(description="Metodo de pago desactivado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def delete(self, request, id_metodo_pago):
        metodo = self._get_metodo(id_metodo_pago)
        if not metodo:
            return Response({'error': 'Metodo de pago no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        metodo.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'DESACTIVAR_METODO_PAGO', f'Metodo de pago desactivado: {metodo.id_metodo_pago}.')
        return Response({'mensaje': 'Metodo de pago desactivado correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU14 - Gestionar Planes de Comision"])
class PlanComisionListCreateView(APIView):
    permission_classes = [EsAdmin]
    serializer_class = PlanComisionSerializer

    @extend_schema(
        summary="Listar planes de comision",
        responses={200: PlanComisionSerializer(many=True)}
    )
    def get(self, request):
        planes = PlanComision.consultar()
        estado_filtro = request.query_params.get('estado')
        codigo_barbero = request.query_params.get('codigo_barbero')
        nombre = request.query_params.get('nombre')

        if estado_filtro:
            planes = planes.filter(estado=estado_filtro.upper())
        if codigo_barbero:
            planes = planes.filter(codigo_barbero_id=codigo_barbero)
        if nombre:
            planes = planes.filter(nombre__icontains=nombre)

        registrar_bitacora(request, 'CONSULTAR_PLANES_COMISION', 'Consulta de planes de comision.')
        return Response(PlanComisionSerializer(planes, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear plan de comision",
        request=PlanComisionSerializer,
        responses={
            201: OpenApiResponse(description="Plan de comision registrado."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Crear plan de comision",
                value={
                    "nombre": "Plan base 60/40",
                    "descripcion": "Comision estandar para servicios generales",
                    "codigo_barbero": "BARB001",
                    "porcentaje_barbero": "60.00",
                    "porcentaje_barberia": "40.00",
                    "fecha_inicio": "2026-06-01",
                    "estado": "ACTIVO",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = PlanComisionSerializer(data=request.data)
        if serializer.is_valid():
            plan = serializer.save()
            registrar_bitacora(request, 'CREAR_PLAN_COMISION', f'Plan de comision creado: {plan.id_plan_comision}.')
            return Response(
                {'mensaje': 'Plan de comision registrado correctamente.', 'plan_comision': PlanComisionSerializer(plan).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU14 - Gestionar Planes de Comision"])
class PlanComisionDetalleView(APIView):
    permission_classes = [EsAdmin]
    serializer_class = PlanComisionSerializer

    def _get_plan(self, id_plan_comision):
        try:
            return PlanComision.consultar().get(pk=id_plan_comision)
        except PlanComision.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de plan de comision",
        responses={200: PlanComisionSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, id_plan_comision):
        plan = self._get_plan(id_plan_comision)
        if not plan:
            return Response({'error': 'Plan de comision no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PlanComisionSerializer(plan).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar plan de comision",
        request=PlanComisionSerializer,
        responses={
            200: OpenApiResponse(description="Plan de comision actualizado."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def put(self, request, id_plan_comision):
        plan = self._get_plan(id_plan_comision)
        if not plan:
            return Response({'error': 'Plan de comision no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        estado_anterior = plan.estado
        serializer = PlanComisionSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            plan = serializer.save()
            accion = accion_estado(plan.estado, 'ACTIVAR_PLAN_COMISION', 'ACTUALIZAR_PLAN_COMISION') if estado_anterior != plan.estado else 'ACTUALIZAR_PLAN_COMISION'
            registrar_bitacora(request, accion, f'Plan de comision actualizado: {plan.id_plan_comision}.')
            return Response(
                {'mensaje': 'Plan de comision actualizado correctamente.', 'plan_comision': PlanComisionSerializer(plan).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar plan de comision",
        responses={200: OpenApiResponse(description="Plan de comision desactivado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def delete(self, request, id_plan_comision):
        plan = self._get_plan(id_plan_comision)
        if not plan:
            return Response({'error': 'Plan de comision no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        plan.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'DESACTIVAR_PLAN_COMISION', f'Plan de comision desactivado: {plan.id_plan_comision}.')
        return Response({'mensaje': 'Plan de comision desactivado correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU18 - Gestionar Caja"])
class CajaEstadoView(APIView):
    permission_classes = [EsAdminOCajero]
    serializer_class = CajaSerializer

    @extend_schema(
        summary="Consultar estado actual de caja",
        responses={200: CajaSerializer, 404: OpenApiResponse(description="No existe una caja abierta.")}
    )
    def get(self, request):
        caja = Caja.caja_abierta()
        if not caja:
            ultima_caja = Caja.consultar().first()
            return Response(
                {
                    'estado': 'SIN_CAJA_ABIERTA',
                    'mensaje': 'No existe una caja abierta.',
                    'ultima_caja': CajaSerializer(ultima_caja).data if ultima_caja else None,
                },
                status=status.HTTP_200_OK
            )

        caja.recalcular_saldo_esperado()
        registrar_bitacora(request, 'CONSULTAR_ESTADO_CAJA', f'Consulta de estado de caja: {caja.id_caja}.')
        return Response(
            {
                'estado': 'ABIERTA',
                'caja': CajaSerializer(caja).data,
            },
            status=status.HTTP_200_OK
        )


@extend_schema(tags=["CU18 - Gestionar Caja"])
class CajaAbrirView(APIView):
    permission_classes = [EsAdminOCajero]
    serializer_class = CajaAperturaSerializer

    @extend_schema(
        summary="Abrir caja",
        request=CajaAperturaSerializer,
        responses={
            201: CajaSerializer,
            400: OpenApiResponse(description="Monto invalido o caja ya abierta."),
            403: OpenApiResponse(description="Usuario sin permiso para operar caja."),
        },
        examples=[
            OpenApiExample(
                "Abrir caja",
                value={"monto_apertura": "250.00"},
                request_only=True,
            )
        ]
    )
    def post(self, request):
        serializer = CajaAperturaSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = getattr(request, 'usuario_actual', None)
        try:
            with transaction.atomic():
                caja = Caja.objects.create(
                    codigo_usuario_apertura=usuario,
                    monto_apertura=serializer.validated_data['monto_apertura'],
                    saldo_esperado=serializer.validated_data['monto_apertura'],
                )
                registrar_bitacora(request, 'ABRIR_CAJA', f'Caja abierta: {caja.id_caja}.')
        except Exception:
            return Response({'error': 'Error al guardar la apertura de caja.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {'mensaje': 'Caja abierta correctamente.', 'caja': CajaSerializer(caja).data},
            status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["CU18 - Gestionar Caja"])
class CajaConsultarView(APIView):
    permission_classes = [EsAdminOCajero]
    serializer_class = CajaSerializer

    @extend_schema(
        summary="Consultar caja abierta",
        responses={
            200: CajaSerializer,
            404: OpenApiResponse(description="No existe una caja abierta."),
            403: OpenApiResponse(description="Usuario sin permiso para operar caja."),
        }
    )
    def get(self, request):
        caja = Caja.caja_abierta()
        if not caja:
            return Response({'error': 'No existe una caja abierta para consultar.'}, status=status.HTTP_404_NOT_FOUND)

        caja.recalcular_saldo_esperado()
        registrar_bitacora(request, 'CONSULTAR_CAJA', f'Consulta de caja abierta: {caja.id_caja}.')
        return Response(
            {'mensaje': 'Caja consultada correctamente.', 'caja': CajaSerializer(caja).data},
            status=status.HTTP_200_OK
        )


@extend_schema(tags=["CU18 - Gestionar Caja"])
class CajaHistorialView(APIView):
    permission_classes = [EsAdminOCajero]
    serializer_class = CajaSerializer

    @extend_schema(
        summary="Consultar historial de cajas",
        responses={
            200: CajaSerializer(many=True),
            403: OpenApiResponse(description="Usuario sin permiso para operar caja."),
        }
    )
    def get(self, request):
        cajas = Caja.consultar()
        estado_filtro = request.query_params.get('estado')
        responsable = request.query_params.get('responsable')
        fecha = request.query_params.get('fecha')

        if estado_filtro:
            cajas = cajas.filter(estado=estado_filtro.upper())
        if responsable:
            cajas = cajas.filter(
                Q(codigo_usuario_apertura__nombre__icontains=responsable)
                | Q(codigo_usuario_apertura__apellido__icontains=responsable)
            )
        if fecha:
            cajas = cajas.filter(
                Q(fecha_apertura__date=fecha)
                | Q(fecha_cierre__date=fecha)
            )

        cajas = list(cajas)
        for caja in cajas:
            caja.recalcular_saldo_esperado()

        registrar_bitacora(request, 'CONSULTAR_HISTORIAL_CAJA', 'Consulta de historial de cajas.')
        return Response(
            {
                'mensaje': 'Historial de cajas consultado correctamente.',
                'cajas': CajaSerializer(cajas, many=True).data,
            },
            status=status.HTTP_200_OK
        )


@extend_schema(tags=["CU18 - Gestionar Caja"])
class CajaCerrarView(APIView):
    permission_classes = [EsAdminOCajero]
    serializer_class = CajaCierreSerializer

    @extend_schema(
        summary="Cerrar caja",
        request=CajaCierreSerializer,
        responses={
            200: CajaSerializer,
            400: OpenApiResponse(description="Monto invalido o cierre sin justificacion requerida."),
            404: OpenApiResponse(description="No existe una caja abierta."),
            403: OpenApiResponse(description="Usuario sin permiso para operar caja."),
        },
        examples=[
            OpenApiExample(
                "Cerrar caja",
                value={"monto_cierre": "500.00", "justificacion_cierre": ""},
                request_only=True,
            ),
            OpenApiExample(
                "Cerrar caja con faltante",
                value={"monto_cierre": "450.00", "justificacion_cierre": "Faltante reportado por pago anulado."},
                request_only=True,
            )
        ]
    )
    def post(self, request):
        caja = Caja.caja_abierta()
        if not caja:
            return Response({'error': 'No existe una caja abierta para cerrar.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = CajaCierreSerializer(data=request.data, context={'caja': caja})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = getattr(request, 'usuario_actual', None)
        try:
            with transaction.atomic():
                caja.cerrar(
                    usuario=usuario,
                    monto_cierre=serializer.validated_data['monto_cierre'],
                    justificacion=serializer.validated_data.get('justificacion_cierre', ''),
                )
                registrar_bitacora(request, 'CERRAR_CAJA', f'Caja cerrada: {caja.id_caja}.')
        except Exception:
            return Response({'error': 'Error al guardar el cierre de caja.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {'mensaje': 'Caja cerrada correctamente.', 'caja': CajaSerializer(caja).data},
            status=status.HTTP_200_OK
        )
