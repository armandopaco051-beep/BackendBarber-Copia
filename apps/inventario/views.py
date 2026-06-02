from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.permissions import EsAdmin
from apps.seguridad.views import registrar_bitacora

from .models import CategoriaProducto, Insumo, Marca, MovimientoInventario, Producto
from .serializers import (
    CategoriaProductoSerializer,
    InsumoSerializer,
    MarcaSerializer,
    MovimientoInventarioSerializer,
    ProductoSerializer,
)


def registrar_movimiento(request, tipo_movimiento, cantidad=0, motivo='', producto=None, insumo=None):
    usuario = getattr(request, 'usuario_actual', None)
    MovimientoInventario.objects.create(
        id_producto=producto,
        id_insumo=insumo,
        tipo_movimiento=tipo_movimiento,
        cantidad=max(0, int(cantidad or 0)),
        motivo=motivo,
        usuario=usuario,
    )


@extend_schema(tags=["CU15/CU16 - Inventario"])
class CategoriaProductoListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(summary="Listar categorias de inventario", responses={200: CategoriaProductoSerializer(many=True)})
    def get(self, request):
        categorias = CategoriaProducto.consultar()
        estado_filtro = request.query_params.get('estado')
        if estado_filtro:
            categorias = categorias.filter(estado=estado_filtro.upper())
        return Response(CategoriaProductoSerializer(categorias, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear categoria de inventario",
        request=CategoriaProductoSerializer,
        responses={201: OpenApiResponse(description="Categoria registrada."), 400: OpenApiResponse(description="Datos invalidos.")}
    )
    def post(self, request):
        serializer = CategoriaProductoSerializer(data=request.data)
        if serializer.is_valid():
            categoria = serializer.save()
            registrar_bitacora(request, 'CREAR_CATEGORIA_INVENTARIO', f'Categoria de inventario creada: {categoria.id_categoria}.')
            return Response({'mensaje': 'Categoria registrada correctamente.', 'categoria': CategoriaProductoSerializer(categoria).data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU15/CU16 - Inventario"])
class CategoriaProductoDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_categoria(self, id_categoria):
        return CategoriaProducto.objects.filter(pk=id_categoria).first()

    def get(self, request, id_categoria):
        categoria = self._get_categoria(id_categoria)
        if not categoria:
            return Response({'error': 'Categoria no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CategoriaProductoSerializer(categoria).data, status=status.HTTP_200_OK)

    def put(self, request, id_categoria):
        categoria = self._get_categoria(id_categoria)
        if not categoria:
            return Response({'error': 'Categoria no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategoriaProductoSerializer(categoria, data=request.data, partial=True)
        if serializer.is_valid():
            categoria = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_CATEGORIA_INVENTARIO', f'Categoria de inventario actualizada: {categoria.id_categoria}.')
            return Response({'mensaje': 'Categoria actualizada correctamente.', 'categoria': CategoriaProductoSerializer(categoria).data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id_categoria):
        categoria = self._get_categoria(id_categoria)
        if not categoria:
            return Response({'error': 'Categoria no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        categoria.estado = 'INACTIVO'
        categoria.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_bitacora(request, 'DESACTIVAR_CATEGORIA_INVENTARIO', f'Categoria de inventario desactivada: {categoria.id_categoria}.')
        return Response({'mensaje': 'Categoria desactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU15/CU16 - Inventario"])
class MarcaListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(summary="Listar marcas", responses={200: MarcaSerializer(many=True)})
    def get(self, request):
        marcas = Marca.consultar()
        estado_filtro = request.query_params.get('estado')
        if estado_filtro:
            marcas = marcas.filter(estado=estado_filtro.upper())
        return Response(MarcaSerializer(marcas, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(summary="Crear marca", request=MarcaSerializer, responses={201: OpenApiResponse(description="Marca registrada."), 400: OpenApiResponse(description="Datos invalidos.")})
    def post(self, request):
        serializer = MarcaSerializer(data=request.data)
        if serializer.is_valid():
            marca = serializer.save()
            registrar_bitacora(request, 'CREAR_MARCA', f'Marca creada: {marca.id_marca}.')
            return Response({'mensaje': 'Marca registrada correctamente.', 'marca': MarcaSerializer(marca).data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU15/CU16 - Inventario"])
class MarcaDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_marca(self, id_marca):
        return Marca.objects.filter(pk=id_marca).first()

    def get(self, request, id_marca):
        marca = self._get_marca(id_marca)
        if not marca:
            return Response({'error': 'Marca no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(MarcaSerializer(marca).data, status=status.HTTP_200_OK)

    def put(self, request, id_marca):
        marca = self._get_marca(id_marca)
        if not marca:
            return Response({'error': 'Marca no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MarcaSerializer(marca, data=request.data, partial=True)
        if serializer.is_valid():
            marca = serializer.save()
            registrar_bitacora(request, 'ACTUALIZAR_MARCA', f'Marca actualizada: {marca.id_marca}.')
            return Response({'mensaje': 'Marca actualizada correctamente.', 'marca': MarcaSerializer(marca).data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id_marca):
        marca = self._get_marca(id_marca)
        if not marca:
            return Response({'error': 'Marca no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        marca.estado = 'INACTIVO'
        marca.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_bitacora(request, 'DESACTIVAR_MARCA', f'Marca desactivada: {marca.id_marca}.')
        return Response({'mensaje': 'Marca desactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU15 - Gestionar Productos"])
class ProductoListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(summary="Listar productos", responses={200: ProductoSerializer(many=True)})
    def get(self, request):
        productos = Producto.consultar()
        estado_filtro = request.query_params.get('estado')
        id_categoria = request.query_params.get('id_categoria')
        stock_bajo = request.query_params.get('stock_bajo')

        if estado_filtro:
            productos = productos.filter(estado=estado_filtro.upper())
        if id_categoria:
            productos = productos.filter(id_categoria_id=id_categoria)
        if stock_bajo and stock_bajo.upper() in ['1', 'TRUE', 'SI']:
            productos = [item for item in productos if item.stock_bajo]

        registrar_bitacora(request, 'CONSULTAR_PRODUCTOS', 'Consulta de productos.')
        data = ProductoSerializer(productos, many=True).data
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear producto",
        request=ProductoSerializer,
        responses={201: OpenApiResponse(description="Producto registrado."), 400: OpenApiResponse(description="Datos invalidos.")},
        examples=[OpenApiExample("Crear producto", value={"id_categoria": 1, "id_marca": 1, "nombre": "Cera matte", "descripcion": "Cera de fijacion media", "precio_venta": "45.00", "cantidad_disponible": 10, "stock_minimo": 3, "tipo_producto": "VENTA", "estado": "ACTIVO"}, request_only=True)]
    )
    def post(self, request):
        serializer = ProductoSerializer(data=request.data)
        if serializer.is_valid():
            producto = serializer.save()
            if producto.cantidad_disponible > 0:
                registrar_movimiento(request, 'ENTRADA_INICIAL', producto.cantidad_disponible, 'Stock inicial del producto', producto=producto)
            registrar_bitacora(request, 'CREAR_PRODUCTO', f'Producto creado: {producto.id_producto}.')
            return Response({'mensaje': 'Producto registrado correctamente.', 'producto': ProductoSerializer(producto).data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU15 - Gestionar Productos"])
class ProductoDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_producto(self, id_producto):
        return Producto.consultar().filter(pk=id_producto).first()

    def get(self, request, id_producto):
        producto = self._get_producto(id_producto)
        if not producto:
            return Response({'error': 'Producto no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProductoSerializer(producto).data, status=status.HTTP_200_OK)

    def put(self, request, id_producto):
        producto = self._get_producto(id_producto)
        if not producto:
            return Response({'error': 'Producto no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        stock_anterior = producto.cantidad_disponible
        estado_anterior = producto.estado
        serializer = ProductoSerializer(producto, data=request.data, partial=True)
        if serializer.is_valid():
            producto = serializer.save()
            if producto.cantidad_disponible != stock_anterior:
                diferencia = abs(producto.cantidad_disponible - stock_anterior)
                registrar_movimiento(
                    request,
                    'AJUSTE',
                    diferencia,
                    f'Ajuste de stock de {stock_anterior} a {producto.cantidad_disponible}.',
                    producto=producto,
                )
            if estado_anterior != producto.estado:
                registrar_movimiento(request, 'ACTIVACION' if producto.estado == 'ACTIVO' else 'DESACTIVACION', 0, f'Cambio de estado a {producto.estado}.', producto=producto)
            registrar_bitacora(request, 'ACTUALIZAR_PRODUCTO', f'Producto actualizado: {producto.id_producto}.')
            return Response({'mensaje': 'Producto actualizado correctamente.', 'producto': ProductoSerializer(producto).data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id_producto):
        producto = self._get_producto(id_producto)
        if not producto:
            return Response({'error': 'Producto no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        producto.estado = 'INACTIVO'
        producto.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_movimiento(request, 'DESACTIVACION', 0, 'Desactivacion logica del producto.', producto=producto)
        registrar_bitacora(request, 'DESACTIVAR_PRODUCTO', f'Producto desactivado: {producto.id_producto}.')
        return Response({'mensaje': 'Producto desactivado correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU15 - Gestionar Productos"])
class ProductoStockBajoView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        productos = [item for item in Producto.consultar().filter(estado='ACTIVO') if item.stock_bajo]
        registrar_bitacora(request, 'CONSULTAR_STOCK_BAJO_PRODUCTOS', 'Consulta de productos con stock bajo.')
        return Response(ProductoSerializer(productos, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU16 - Gestionar Insumos"])
class InsumoListCreateView(APIView):
    permission_classes = [EsAdmin]

    @extend_schema(summary="Listar insumos", responses={200: InsumoSerializer(many=True)})
    def get(self, request):
        insumos = Insumo.consultar()
        estado_filtro = request.query_params.get('estado')
        id_categoria = request.query_params.get('id_categoria')
        stock_minimo = request.query_params.get('stock_minimo')

        if estado_filtro:
            insumos = insumos.filter(estado=estado_filtro.upper())
        if id_categoria:
            insumos = insumos.filter(id_categoria_id=id_categoria)
        if stock_minimo and stock_minimo.upper() in ['1', 'TRUE', 'SI']:
            insumos = [item for item in insumos if item.stock_bajo]

        registrar_bitacora(request, 'CONSULTAR_INSUMOS', 'Consulta de insumos.')
        return Response(InsumoSerializer(insumos, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear insumo",
        request=InsumoSerializer,
        responses={201: OpenApiResponse(description="Insumo registrado."), 400: OpenApiResponse(description="Datos invalidos.")},
        examples=[OpenApiExample("Crear insumo", value={"id_categoria": 1, "nombre": "Talco", "descripcion": "Talco para cuello", "unidad_medida": "botella", "cantidad_disponible": 8, "stock_minimo": 2, "estado": "ACTIVO"}, request_only=True)]
    )
    def post(self, request):
        serializer = InsumoSerializer(data=request.data)
        if serializer.is_valid():
            insumo = serializer.save()
            if insumo.cantidad_disponible > 0:
                registrar_movimiento(request, 'ENTRADA_INICIAL', insumo.cantidad_disponible, 'Stock inicial del insumo', insumo=insumo)
            registrar_bitacora(request, 'CREAR_INSUMO', f'Insumo creado: {insumo.id_insumo}.')
            return Response({'mensaje': 'Insumo registrado correctamente.', 'insumo': InsumoSerializer(insumo).data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["CU16 - Gestionar Insumos"])
class InsumoDetalleView(APIView):
    permission_classes = [EsAdmin]

    def _get_insumo(self, id_insumo):
        return Insumo.consultar().filter(pk=id_insumo).first()

    def get(self, request, id_insumo):
        insumo = self._get_insumo(id_insumo)
        if not insumo:
            return Response({'error': 'Insumo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(InsumoSerializer(insumo).data, status=status.HTTP_200_OK)

    def put(self, request, id_insumo):
        insumo = self._get_insumo(id_insumo)
        if not insumo:
            return Response({'error': 'Insumo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        stock_anterior = insumo.cantidad_disponible
        estado_anterior = insumo.estado
        serializer = InsumoSerializer(insumo, data=request.data, partial=True)
        if serializer.is_valid():
            insumo = serializer.save()
            if insumo.cantidad_disponible != stock_anterior:
                diferencia = abs(insumo.cantidad_disponible - stock_anterior)
                registrar_movimiento(
                    request,
                    'AJUSTE',
                    diferencia,
                    f'Ajuste de stock de {stock_anterior} a {insumo.cantidad_disponible}.',
                    insumo=insumo,
                )
            if estado_anterior != insumo.estado:
                registrar_movimiento(request, 'ACTIVACION' if insumo.estado == 'ACTIVO' else 'DESACTIVACION', 0, f'Cambio de estado a {insumo.estado}.', insumo=insumo)
            registrar_bitacora(request, 'ACTUALIZAR_INSUMO', f'Insumo actualizado: {insumo.id_insumo}.')
            return Response({'mensaje': 'Insumo actualizado correctamente.', 'insumo': InsumoSerializer(insumo).data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id_insumo):
        insumo = self._get_insumo(id_insumo)
        if not insumo:
            return Response({'error': 'Insumo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        insumo.estado = 'INACTIVO'
        insumo.save(update_fields=['estado', 'fecha_actualizacion'])
        registrar_movimiento(request, 'DESACTIVACION', 0, 'Desactivacion logica del insumo.', insumo=insumo)
        registrar_bitacora(request, 'DESACTIVAR_INSUMO', f'Insumo desactivado: {insumo.id_insumo}.')
        return Response({'mensaje': 'Insumo desactivado correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=["CU16 - Gestionar Insumos"])
class InsumoStockMinimoView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        insumos = [item for item in Insumo.consultar().filter(estado='ACTIVO') if item.stock_bajo]
        registrar_bitacora(request, 'CONSULTAR_STOCK_MINIMO_INSUMOS', 'Consulta de insumos con stock minimo.')
        return Response(InsumoSerializer(insumos, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=["CU15/CU16 - Inventario"])
class MovimientoInventarioListView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        movimientos = MovimientoInventario.consultar()
        id_producto = request.query_params.get('id_producto')
        id_insumo = request.query_params.get('id_insumo')
        if id_producto:
            movimientos = movimientos.filter(id_producto_id=id_producto)
        if id_insumo:
            movimientos = movimientos.filter(id_insumo_id=id_insumo)
        return Response(MovimientoInventarioSerializer(movimientos, many=True).data, status=status.HTTP_200_OK)
