from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from apps.seguridad.permissions import EsAdmin, EsAdminOLecturaAutenticada
from apps.seguridad.views import registrar_bitacora

from .models import CategoriaServicio, Servicio
from .serializers import CategoriaServicioSerializer, ServicioSerializer


# CRUD de CU6 Gestionar categorias.
# GET lista categorias y POST crea una nueva categoria.
@extend_schema(tags=["CU6 - Gestionar Categorias"])
class CategoriaServicioListCreateView(APIView):
    permission_classes = [EsAdminOLecturaAutenticada]

    @extend_schema(
        summary="Listar categorias de servicios",
        responses={200: CategoriaServicioSerializer(many=True)}
    )
    def get(self, request):
        # Permite filtrar por estado: ACTIVO o INACTIVO.
        categorias = CategoriaServicio.objects.all()
        estado_filtro = request.query_params.get('estado')
        if estado_filtro:
            categorias = categorias.filter(estado=estado_filtro.upper())
        registrar_bitacora(request, 'CONSULTAR_CATEGORIAS_SERVICIO', 'Consulta de categorias de servicios.')
        return Response(CategoriaServicioSerializer(categorias, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear categoria de servicio",
        request=CategoriaServicioSerializer,
        responses={
            201: OpenApiResponse(description="Categoria registrada."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Crear categoria",
                value={"nombre": "Cortes", "descripcion": "Servicios de corte de cabello", "estado": "ACTIVO"},
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Crea una categoria y registra la accion en bitacora.
        serializer = CategoriaServicioSerializer(data=request.data)
        if serializer.is_valid():
            categoria = serializer.save()
            registrar_bitacora(request, 'CREAR_CATEGORIA_SERVICIO', f'Categoria creada: {categoria.nombre}.')
            return Response(
                {'mensaje': 'Categoria registrada correctamente.', 'categoria': CategoriaServicioSerializer(categoria).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# CRUD de detalle para categorias.
# GET consulta, PUT actualiza y DELETE desactiva la categoria.
@extend_schema(tags=["CU6 - Gestionar Categorias"])
class CategoriaServicioDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_categoria(self, id_categoria):
        # Metodo auxiliar para reutilizar busqueda y devolver None si no existe.
        try:
            return CategoriaServicio.objects.get(pk=id_categoria)
        except CategoriaServicio.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de categoria",
        responses={200: CategoriaServicioSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_categoria):
        categoria = self._get_categoria(id_categoria)
        if not categoria:
            return Response({'error': 'Categoria no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CategoriaServicioSerializer(categoria).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar categoria",
        request=CategoriaServicioSerializer,
        responses={
            200: OpenApiResponse(description="Categoria actualizada."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_categoria):
        categoria = self._get_categoria(id_categoria)
        if not categoria:
            return Response({'error': 'Categoria no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategoriaServicioSerializer(categoria, data=request.data, partial=True)
        if serializer.is_valid():
            categoria = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_CATEGORIA_SERVICIO', f'Categoria actualizada: {categoria.id_categoria}.')
            return Response(
                {'mensaje': 'Categoria actualizada correctamente.', 'categoria': CategoriaServicioSerializer(categoria).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar categoria",
        description="No elimina la categoria; la deja como INACTIVO.",
        responses={200: OpenApiResponse(description="Categoria desactivada."), 404: OpenApiResponse(description="No encontrada.")}
    )
    def delete(self, request, id_categoria):
        # No se elimina fisicamente: se cambia estado a INACTIVO para conservar historial.
        categoria = self._get_categoria(id_categoria)
        if not categoria:
            return Response({'error': 'Categoria no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        categoria.estado = 'INACTIVO'
        categoria.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_bitacora(request, 'DESACTIVAR_CATEGORIA_SERVICIO', f'Categoria desactivada: {categoria.id_categoria}.')
        return Response({'mensaje': 'Categoria desactivada correctamente.'}, status=status.HTTP_200_OK)


# CRUD de CU10 Gestionar servicios.
# GET lista servicios y POST crea un nuevo servicio.
@extend_schema(tags=["CU10 - Gestionar Servicios"])
class ServicioListCreateView(APIView):
    permission_classes = [EsAdminOLecturaAutenticada]

    @extend_schema(
        summary="Listar servicios",
        description="Lista servicios. Permite filtrar por id_categoria, estado y nombre.",
        responses={200: ServicioSerializer(many=True)}
    )
    def get(self, request):
        # Filtros utiles para frontend: categoria, estado y busqueda por nombre.
        servicios = Servicio.objects.select_related('id_categoria').all()

        id_categoria = request.query_params.get('id_categoria')
        estado_filtro = request.query_params.get('estado')
        nombre = request.query_params.get('nombre')

        if id_categoria:
            servicios = servicios.filter(id_categoria_id=id_categoria)
        if estado_filtro:
            servicios = servicios.filter(estado=estado_filtro.upper())
        if nombre:
            servicios = servicios.filter(nombre__icontains=nombre)

        registrar_bitacora(request, 'CONSULTAR_SERVICIOS', 'Consulta de servicios.')
        return Response(ServicioSerializer(servicios, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear servicio",
        request=ServicioSerializer,
        responses={
            201: OpenApiResponse(description="Servicio registrado."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Crear servicio",
                value={
                    "id_categoria": 1,
                    "nombre": "Corte clasico",
                    "descripcion": "Corte tradicional con maquina y tijera",
                    "precio": "40.00",
                    "duracion_minutos": 45,
                    "estado": "ACTIVO",
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Crea el servicio validando categoria, precio, duracion y duplicados.
        serializer = ServicioSerializer(data=request.data)
        if serializer.is_valid():
            servicio = serializer.save()
            registrar_bitacora(request, 'CREAR_SERVICIO', f'Servicio creado: {servicio.nombre}.')
            return Response(
                {'mensaje': 'Servicio registrado correctamente.', 'servicio': ServicioSerializer(servicio).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# CRUD de detalle para servicios.
# GET consulta, PUT actualiza y DELETE desactiva el servicio.
@extend_schema(tags=["CU10 - Gestionar Servicios"])
class ServicioDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_servicio(self, id_servicio):
        # Busca el servicio con su categoria para evitar consultas adicionales.
        try:
            return Servicio.objects.select_related('id_categoria').get(pk=id_servicio)
        except Servicio.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de servicio",
        responses={200: ServicioSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, id_servicio):
        servicio = self._get_servicio(id_servicio)
        if not servicio:
            return Response({'error': 'Servicio no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ServicioSerializer(servicio).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar servicio",
        request=ServicioSerializer,
        responses={
            200: OpenApiResponse(description="Servicio actualizado."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def put(self, request, id_servicio):
        servicio = self._get_servicio(id_servicio)
        if not servicio:
            return Response({'error': 'Servicio no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ServicioSerializer(servicio, data=request.data, partial=True)
        if serializer.is_valid():
            servicio = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_SERVICIO', f'Servicio actualizado: {servicio.id_servicio}.')
            return Response(
                {'mensaje': 'Servicio actualizado correctamente.', 'servicio': ServicioSerializer(servicio).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar servicio",
        description="No elimina el servicio; lo deja como INACTIVO.",
        responses={200: OpenApiResponse(description="Servicio desactivado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def delete(self, request, id_servicio):
        # Desactiva el servicio para que ya no pueda reservarse en citas.
        servicio = self._get_servicio(id_servicio)
        if not servicio:
            return Response({'error': 'Servicio no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        servicio.estado = 'INACTIVO'
        servicio.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_bitacora(request, 'DESACTIVAR_SERVICIO', f'Servicio desactivado: {servicio.id_servicio}.')
        return Response({'mensaje': 'Servicio desactivado correctamente.'}, status=status.HTTP_200_OK)
