from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from apps.seguridad.permissions import EsAdmin, EsAdminOLecturaAutenticada, EsCualquierUsuario
from apps.seguridad.views import registrar_bitacora

from .models import CategoriaServicio, PaqueteServicio, RecomendacionCuidado, Servicio
from .serializers import CategoriaServicioSerializer, PaqueteServicioSerializer, RecomendacionCuidadoSerializer, ServicioSerializer


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


# CRUD de CU28 Gestionar paquetes de servicios.
# GET lista paquetes y POST crea un paquete con varios servicios incluidos.
@extend_schema(tags=["CU28 - Gestionar Paquetes de Servicios"])
class PaqueteServicioListCreateView(APIView):
    permission_classes = [EsAdminOLecturaAutenticada]

    @extend_schema(
        summary="Listar paquetes de servicios",
        description="Lista paquetes. Permite filtrar por estado, nombre y servicio incluido.",
        responses={200: PaqueteServicioSerializer(many=True)}
    )
    def get(self, request):
        # Filtros para que el frontend muestre ofertas disponibles o busque por servicio.
        paquetes = PaqueteServicio.consultar().all()
        estado_filtro = request.query_params.get('estado')
        nombre = request.query_params.get('nombre')
        id_servicio = request.query_params.get('id_servicio')

        if estado_filtro:
            paquetes = paquetes.filter(estado=estado_filtro.upper())
        if nombre:
            paquetes = paquetes.filter(nombre__icontains=nombre)
        if id_servicio:
            paquetes = paquetes.filter(servicios__id_servicio=id_servicio)

        registrar_bitacora(request, 'CONSULTAR_PAQUETES_SERVICIO', 'Consulta de paquetes de servicios.')
        return Response(PaqueteServicioSerializer(paquetes.distinct(), many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear paquete de servicios",
        request=PaqueteServicioSerializer,
        responses={
            201: OpenApiResponse(description="Paquete registrado."),
            400: OpenApiResponse(description="Datos invalidos."),
        },
        examples=[
            OpenApiExample(
                "Crear paquete",
                value={
                    "nombre": "Corte con barba",
                    "descripcion": "Corte de cabello mas perfilado de barba",
                    "precio_total": "70.00",
                    "duracion_minutos": 75,
                    "estado": "ACTIVO",
                    "servicios": [1, 2],
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Crea el paquete y sus detalles, validando servicios activos, precio y duracion.
        serializer = PaqueteServicioSerializer(data=request.data)
        if serializer.is_valid():
            paquete = serializer.save()
            registrar_bitacora(request, 'CREAR_PAQUETE_SERVICIO', f'Paquete creado: {paquete.id_paquete}.')
            return Response(
                {'mensaje': 'Paquete de servicios registrado correctamente.', 'paquete': PaqueteServicioSerializer(paquete).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# CRUD de detalle para paquetes.
# GET consulta, PUT actualiza composicion/precio/duracion y DELETE inactiva el paquete.
@extend_schema(tags=["CU28 - Gestionar Paquetes de Servicios"])
class PaqueteServicioDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_paquete(self, id_paquete):
        # Busca el paquete con sus servicios incluidos para responder completo.
        try:
            return PaqueteServicio.consultar().get(pk=id_paquete)
        except PaqueteServicio.DoesNotExist:
            return None

    @extend_schema(
        summary="Ver detalle de paquete de servicios",
        responses={200: PaqueteServicioSerializer, 404: OpenApiResponse(description="No encontrado.")}
    )
    def get(self, request, id_paquete):
        paquete = self._get_paquete(id_paquete)
        if not paquete:
            return Response({'error': 'Paquete de servicios no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaqueteServicioSerializer(paquete).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar paquete de servicios",
        request=PaqueteServicioSerializer,
        responses={
            200: OpenApiResponse(description="Paquete actualizado."),
            400: OpenApiResponse(description="Datos invalidos."),
            404: OpenApiResponse(description="No encontrado."),
        }
    )
    def put(self, request, id_paquete):
        # Permite modificar datos generales y reemplazar los servicios incluidos.
        paquete = self._get_paquete(id_paquete)
        if not paquete:
            return Response({'error': 'Paquete de servicios no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PaqueteServicioSerializer(paquete, data=request.data, partial=True)
        if serializer.is_valid():
            paquete = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_PAQUETE_SERVICIO', f'Paquete actualizado: {paquete.id_paquete}.')
            return Response(
                {'mensaje': 'Paquete de servicios actualizado correctamente.', 'paquete': PaqueteServicioSerializer(paquete).data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Desactivar paquete de servicios",
        description="No elimina el paquete; lo deja como INACTIVO.",
        responses={200: OpenApiResponse(description="Paquete desactivado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def delete(self, request, id_paquete):
        # Inactivacion logica: conserva la oferta y su composicion para historial.
        paquete = self._get_paquete(id_paquete)
        if not paquete:
            return Response({'error': 'Paquete de servicios no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        paquete.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'DESACTIVAR_PAQUETE_SERVICIO', f'Paquete desactivado: {paquete.id_paquete}.')
        return Response({'mensaje': 'Paquete de servicios desactivado correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU28 - Gestionar Paquetes de Servicios"])
class PaqueteServicioActivarView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(
        summary="Activar paquete de servicios",
        responses={200: OpenApiResponse(description="Paquete activado."), 404: OpenApiResponse(description="No encontrado.")}
    )
    def post(self, request, id_paquete):
        # Reactiva el paquete para que vuelva a mostrarse como oferta disponible.
        paquete = PaqueteServicio.consultar().filter(pk=id_paquete).first()
        if not paquete:
            return Response({'error': 'Paquete de servicios no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        paquete.cambiar_estado('ACTIVO')
        registrar_bitacora(request, 'ACTIVAR_PAQUETE_SERVICIO', f'Paquete activado: {paquete.id_paquete}.')
        return Response(
            {'mensaje': 'Paquete de servicios activado correctamente.', 'paquete': PaqueteServicioSerializer(paquete).data},
            status=status.HTTP_200_OK
        )


# CRUD de CU29 Gestionar recomendaciones de cuidado.
# Barberos registran recomendaciones y clientes/barberos pueden consultarlas luego.
@extend_schema(tags=["CU29 - Gestionar Recomendaciones de Cuidado"])
class RecomendacionCuidadoListCreateView(APIView):
    permission_classes = [EsCualquierUsuario]

    def _filtrar_por_usuario(self, queryset, request):
        # Admin ve todo; barbero solo sus recomendaciones; cliente solo las recibidas.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario:
            return queryset.none()
        if usuario.es_admin:
            return queryset
        if usuario.es_barbero:
            return queryset.filter(codigo_barbero=usuario)
        if usuario.es_cliente:
            return queryset.filter(codigo_cliente=usuario, estado='ACTIVO')
        return queryset.none()

    @extend_schema(
        summary="Listar recomendaciones de cuidado",
        description="Permite filtrar por cliente, barbero, atencion y estado respetando el rol autenticado.",
        responses={200: RecomendacionCuidadoSerializer(many=True)}
    )
    def get(self, request):
        recomendaciones = self._filtrar_por_usuario(RecomendacionCuidado.consultar().all(), request)
        codigo_cliente = request.query_params.get('codigo_cliente')
        codigo_barbero = request.query_params.get('codigo_barbero')
        id_atencion = request.query_params.get('id_atencion')
        estado_filtro = request.query_params.get('estado')

        if codigo_cliente:
            recomendaciones = recomendaciones.filter(codigo_cliente_id=codigo_cliente)
        if codigo_barbero:
            recomendaciones = recomendaciones.filter(codigo_barbero_id=codigo_barbero)
        if id_atencion:
            recomendaciones = recomendaciones.filter(id_atencion_id=id_atencion)
        if estado_filtro:
            recomendaciones = recomendaciones.filter(estado=estado_filtro.upper())

        registrar_bitacora(request, 'CONSULTAR_RECOMENDACIONES_CUIDADO', 'Consulta de recomendaciones de cuidado.')
        return Response(RecomendacionCuidadoSerializer(recomendaciones, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Registrar recomendacion de cuidado",
        request=RecomendacionCuidadoSerializer,
        responses={
            201: OpenApiResponse(description="Recomendacion registrada."),
            400: OpenApiResponse(description="Datos invalidos."),
            403: OpenApiResponse(description="Usuario sin permiso."),
        },
        examples=[
            OpenApiExample(
                "Registrar recomendacion",
                value={
                    "id_atencion": 1,
                    "contenido": "Usar shampoo hidratante y evitar calor directo durante 48 horas.",
                    "frecuencia_corte": "Cada 3 semanas",
                    "cuidados_cabello": "Aplicar cera ligera solo en puntas.",
                    "productos_sugeridos": [1, 2],
                },
                request_only=True,
            )
        ]
    )
    def post(self, request):
        # Solo barberos o administradores pueden registrar recomendaciones.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or not (usuario.es_barbero or usuario.es_admin):
            return Response({'error': 'Solo barberos o administradores pueden registrar recomendaciones.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = RecomendacionCuidadoSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            recomendacion = serializer.save()
            registrar_bitacora(request, 'CREAR_RECOMENDACION_CUIDADO', f'Recomendacion creada: {recomendacion.id_recomendacion}.')
            return Response(
                {
                    'mensaje': 'Recomendacion de cuidado registrada correctamente.',
                    'recomendacion': RecomendacionCuidadoSerializer(recomendacion).data,
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU29 - Gestionar Recomendaciones de Cuidado"])
class RecomendacionCuidadoDetalleView(APIView):
    permission_classes = [EsCualquierUsuario]

    def _get_recomendacion(self, id_recomendacion, request):
        # Aplica el mismo filtro por rol usado en listados.
        queryset = RecomendacionCuidado.consultar()
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario:
            return None
        if usuario.es_barbero:
            queryset = queryset.filter(codigo_barbero=usuario)
        elif usuario.es_cliente:
            queryset = queryset.filter(codigo_cliente=usuario, estado='ACTIVO')
        elif not usuario.es_admin:
            return None
        return queryset.filter(pk=id_recomendacion).first()

    @extend_schema(
        summary="Ver detalle de recomendacion de cuidado",
        responses={200: RecomendacionCuidadoSerializer, 404: OpenApiResponse(description="No encontrada.")}
    )
    def get(self, request, id_recomendacion):
        recomendacion = self._get_recomendacion(id_recomendacion, request)
        if not recomendacion:
            return Response({'error': 'Recomendacion de cuidado no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(RecomendacionCuidadoSerializer(recomendacion).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar recomendacion de cuidado",
        request=RecomendacionCuidadoSerializer,
        responses={
            200: OpenApiResponse(description="Recomendacion actualizada."),
            400: OpenApiResponse(description="Datos invalidos."),
            403: OpenApiResponse(description="Usuario sin permiso."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def put(self, request, id_recomendacion):
        # Solo el barbero dueno o el administrador pueden modificarla.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or usuario.es_cliente:
            return Response({'error': 'No tiene permiso para modificar recomendaciones.'}, status=status.HTTP_403_FORBIDDEN)
        recomendacion = self._get_recomendacion(id_recomendacion, request)
        if not recomendacion:
            return Response({'error': 'Recomendacion de cuidado no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = RecomendacionCuidadoSerializer(recomendacion, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            recomendacion = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_RECOMENDACION_CUIDADO', f'Recomendacion actualizada: {recomendacion.id_recomendacion}.')
            return Response(
                {
                    'mensaje': 'Recomendacion de cuidado actualizada correctamente.',
                    'recomendacion': RecomendacionCuidadoSerializer(recomendacion).data,
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Inactivar recomendacion de cuidado",
        description="No elimina la recomendacion; la deja como INACTIVO.",
        responses={
            200: OpenApiResponse(description="Recomendacion inactivada."),
            403: OpenApiResponse(description="Usuario sin permiso."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def delete(self, request, id_recomendacion):
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or usuario.es_cliente:
            return Response({'error': 'No tiene permiso para inactivar recomendaciones.'}, status=status.HTTP_403_FORBIDDEN)
        recomendacion = self._get_recomendacion(id_recomendacion, request)
        if not recomendacion:
            return Response({'error': 'Recomendacion de cuidado no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        recomendacion.cambiar_estado('INACTIVO')
        registrar_bitacora(request, 'INACTIVAR_RECOMENDACION_CUIDADO', f'Recomendacion inactivada: {recomendacion.id_recomendacion}.')
        return Response({'mensaje': 'Recomendacion de cuidado inactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU29 - Gestionar Recomendaciones de Cuidado"])
class RecomendacionCuidadoActivarView(APIView):
    permission_classes = [EsCualquierUsuario]

    @extend_schema(
        summary="Activar recomendacion de cuidado",
        responses={
            200: OpenApiResponse(description="Recomendacion activada."),
            403: OpenApiResponse(description="Usuario sin permiso."),
            404: OpenApiResponse(description="No encontrada."),
        }
    )
    def post(self, request, id_recomendacion):
        # Reactiva una recomendacion inactiva para que vuelva a ser consultable por el cliente.
        usuario = getattr(request, 'usuario_actual', None)
        if not usuario or usuario.es_cliente:
            return Response({'error': 'No tiene permiso para activar recomendaciones.'}, status=status.HTTP_403_FORBIDDEN)

        queryset = RecomendacionCuidado.consultar()
        if usuario.es_barbero:
            queryset = queryset.filter(codigo_barbero=usuario)
        elif not usuario.es_admin:
            return Response({'error': 'No tiene permiso para activar recomendaciones.'}, status=status.HTTP_403_FORBIDDEN)

        recomendacion = queryset.filter(pk=id_recomendacion).first()
        if not recomendacion:
            return Response({'error': 'Recomendacion de cuidado no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        recomendacion.cambiar_estado('ACTIVO')
        registrar_bitacora(request, 'ACTIVAR_RECOMENDACION_CUIDADO', f'Recomendacion activada: {recomendacion.id_recomendacion}.')
        return Response(
            {
                'mensaje': 'Recomendacion de cuidado activada correctamente.',
                'recomendacion': RecomendacionCuidadoSerializer(recomendacion).data,
            },
            status=status.HTTP_200_OK
        )
