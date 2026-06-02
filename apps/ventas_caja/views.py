from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.permissions import EsAdmin
from apps.seguridad.views import registrar_bitacora

from .models import MetodoPago, PlanComision
from .serializers import MetodoPagoSerializer, PlanComisionSerializer


def accion_estado(estado, accion_activar, accion_actualizar):
    return accion_activar if estado == 'ACTIVO' else accion_actualizar


@extend_schema(tags=["CU13 - Gestionar Metodos de Pago"])
class MetodoPagoListCreateView(APIView):
    permission_classes = [EsAdmin]

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
