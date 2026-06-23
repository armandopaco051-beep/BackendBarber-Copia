from drf_spectacular.utils import OpenApiParameter, extend_schema
from django.db import models
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.citas.models import DetallePromocion
from apps.inventario.models import Producto
from apps.seguridad.permissions import EsAdmin
from apps.seguridad.views import registrar_bitacora
from apps.ventas_caja.models import Caja, ComisionVenta, DetalleVenta, MovimientoCaja, Venta

from .utils import parse_bool, parse_date, report_response


def _fecha_rango(queryset, request, field='fecha_registro'):
    fecha_inicio = parse_date(request.query_params.get('fecha_inicio'))
    fecha_fin = parse_date(request.query_params.get('fecha_fin'))
    if fecha_inicio:
        queryset = queryset.filter(**{f'{field}__date__gte': fecha_inicio})
    if fecha_fin:
        queryset = queryset.filter(**{f'{field}__date__lte': fecha_fin})
    return queryset


def _common_report_params():
    return [
        OpenApiParameter('formato', str, enum=['pdf', 'excel'], required=False),
        OpenApiParameter('fecha_inicio', str, required=False),
        OpenApiParameter('fecha_fin', str, required=False),
    ]


def _ventas_base(request):
    ventas = _fecha_rango(Venta.consultar(), request)
    estado = request.query_params.get('estado_venta')
    cliente = request.query_params.get('cliente')
    cajero = request.query_params.get('cajero')
    barbero = request.query_params.get('barbero')
    id_metodo_pago = request.query_params.get('id_metodo_pago')
    tipo_item = request.query_params.get('tipo_item')
    id_servicio = request.query_params.get('id_servicio')
    id_producto = request.query_params.get('id_producto')

    if estado:
        ventas = ventas.filter(estado=estado.upper())
    if cliente:
        ventas = ventas.filter(
            Q(codigo_cliente__codigo__icontains=cliente)
            | Q(codigo_cliente__nombre__icontains=cliente)
            | Q(codigo_cliente__apellido__icontains=cliente)
        )
    if cajero:
        ventas = ventas.filter(codigo_cajero_id=cajero)
    if barbero:
        ventas = ventas.filter(detalles__codigo_barbero_id=barbero)
    if id_metodo_pago:
        ventas = ventas.filter(pagos__id_metodo_pago_id=id_metodo_pago)
    if tipo_item:
        ventas = ventas.filter(detalles__tipo_item=tipo_item.upper())
    if id_servicio:
        ventas = ventas.filter(detalles__id_servicio_id=id_servicio)
    if id_producto:
        ventas = ventas.filter(detalles__id_producto_id=id_producto)
    return ventas.distinct()


def _dict_rows(keys, rows):
    return [dict(zip(keys, row)) for row in rows]


def _preview_response(columnas, keys, rows):
    return Response({
        'columnas': columnas,
        'filas': _dict_rows(keys, rows),
    })


def _ventas_data(request):
    ventas = _ventas_base(request)
    headers = ['ID', 'Fecha', 'Cliente', 'Cajero', 'Estado', 'Subtotal', 'Descuento', 'Total']
    keys = ['venta', 'fecha', 'cliente', 'cajero', 'estado', 'subtotal', 'descuento', 'total']
    rows = []
    for venta in ventas:
        cliente = f'{venta.codigo_cliente.nombre} {venta.codigo_cliente.apellido}' if venta.codigo_cliente else 'Consumidor final'
        rows.append([
            venta.id_venta,
            venta.fecha_registro.strftime('%Y-%m-%d %H:%M'),
            cliente,
            venta.codigo_cajero_id,
            venta.estado,
            venta.subtotal,
            venta.descuento,
            venta.total,
        ])
    return headers, keys, rows


def _productos_vendidos_data(request):
    detalles = DetalleVenta.objects.select_related(
        'id_venta',
        'id_producto',
        'id_producto__id_categoria',
        'id_producto__id_marca',
        'id_venta__codigo_cliente',
        'id_venta__codigo_cajero',
    ).filter(tipo_item='PRODUCTO')
    detalles = _fecha_rango(detalles, request, 'id_venta__fecha_registro')

    estado = request.query_params.get('estado_venta')
    if estado:
        detalles = detalles.filter(id_venta__estado=estado.upper())
    if request.query_params.get('id_producto'):
        detalles = detalles.filter(id_producto_id=request.query_params['id_producto'])
    if request.query_params.get('id_categoria_producto'):
        detalles = detalles.filter(id_producto__id_categoria_id=request.query_params['id_categoria_producto'])
    if request.query_params.get('id_marca'):
        detalles = detalles.filter(id_producto__id_marca_id=request.query_params['id_marca'])
    if request.query_params.get('cliente'):
        cliente = request.query_params['cliente']
        detalles = detalles.filter(
            Q(id_venta__codigo_cliente__codigo__icontains=cliente)
            | Q(id_venta__codigo_cliente__nombre__icontains=cliente)
            | Q(id_venta__codigo_cliente__apellido__icontains=cliente)
        )
    if request.query_params.get('cajero'):
        detalles = detalles.filter(id_venta__codigo_cajero_id=request.query_params['cajero'])
    if request.query_params.get('id_metodo_pago'):
        detalles = detalles.filter(id_venta__pagos__id_metodo_pago_id=request.query_params['id_metodo_pago'])

    headers = ['Venta', 'Fecha', 'Producto', 'Categoria', 'Marca', 'Cantidad', 'Precio', 'Subtotal']
    keys = ['venta', 'fecha', 'producto', 'categoria', 'marca', 'cantidad', 'precio', 'subtotal']
    rows = [[
        d.id_venta_id,
        d.id_venta.fecha_registro.strftime('%Y-%m-%d %H:%M'),
        d.id_producto.nombre,
        d.id_producto.id_categoria.nombre,
        d.id_producto.id_marca.nombre if d.id_producto.id_marca else '',
        d.cantidad,
        d.precio_unitario,
        d.subtotal,
    ] for d in detalles.distinct()]
    return headers, keys, rows


def _servicios_realizados_data(request):
    detalles = DetalleVenta.objects.select_related(
        'id_venta',
        'id_servicio',
        'id_servicio__id_categoria',
        'codigo_barbero',
        'id_venta__codigo_cliente',
    ).filter(tipo_item='SERVICIO')
    detalles = _fecha_rango(detalles, request, 'id_venta__fecha_registro')

    if request.query_params.get('estado_venta'):
        detalles = detalles.filter(id_venta__estado=request.query_params['estado_venta'].upper())
    if request.query_params.get('id_servicio'):
        detalles = detalles.filter(id_servicio_id=request.query_params['id_servicio'])
    if request.query_params.get('id_categoria_servicio'):
        detalles = detalles.filter(id_servicio__id_categoria_id=request.query_params['id_categoria_servicio'])
    if request.query_params.get('barbero'):
        detalles = detalles.filter(codigo_barbero_id=request.query_params['barbero'])
    if request.query_params.get('cliente'):
        cliente = request.query_params['cliente']
        detalles = detalles.filter(
            Q(id_venta__codigo_cliente__codigo__icontains=cliente)
            | Q(id_venta__codigo_cliente__nombre__icontains=cliente)
            | Q(id_venta__codigo_cliente__apellido__icontains=cliente)
        )
    if request.query_params.get('cajero'):
        detalles = detalles.filter(id_venta__codigo_cajero_id=request.query_params['cajero'])
    if request.query_params.get('id_metodo_pago'):
        detalles = detalles.filter(id_venta__pagos__id_metodo_pago_id=request.query_params['id_metodo_pago'])
    promocion = parse_bool(request.query_params.get('promocion_aplicada'))
    if promocion is not None:
        servicio_ids = DetallePromocion.objects.values_list('id_servicio_id', flat=True)
        detalles = detalles.filter(id_servicio_id__in=servicio_ids) if promocion else detalles.exclude(id_servicio_id__in=servicio_ids)

    headers = ['Venta', 'Fecha', 'Servicio', 'Categoria', 'Barbero', 'Cantidad', 'Precio', 'Subtotal']
    keys = ['venta', 'fecha', 'servicio', 'categoria', 'barbero', 'cantidad', 'precio', 'subtotal']
    rows = [[
        d.id_venta_id,
        d.id_venta.fecha_registro.strftime('%Y-%m-%d %H:%M'),
        d.id_servicio.nombre,
        d.id_servicio.id_categoria.nombre,
        d.codigo_barbero_id,
        d.cantidad,
        d.precio_unitario,
        d.subtotal,
    ] for d in detalles.distinct()]
    return headers, keys, rows


def _caja_movimientos_data(request):
    movimientos = MovimientoCaja.consultar()
    movimientos = _fecha_rango(movimientos, request, 'fecha')

    if request.query_params.get('estado_caja'):
        movimientos = movimientos.filter(caja__estado=request.query_params['estado_caja'].upper())
    if request.query_params.get('responsable'):
        responsable = request.query_params['responsable']
        movimientos = movimientos.filter(
            Q(usuario__codigo__icontains=responsable)
            | Q(usuario__nombre__icontains=responsable)
            | Q(usuario__apellido__icontains=responsable)
        )
    con_diferencia = parse_bool(request.query_params.get('con_diferencia'))
    if con_diferencia is not None:
        movimientos = movimientos.exclude(caja__diferencia=0) if con_diferencia else movimientos.filter(Q(caja__diferencia=0) | Q(caja__diferencia__isnull=True))
    if request.query_params.get('tipo_movimiento'):
        movimientos = movimientos.filter(tipo_movimiento=request.query_params['tipo_movimiento'].upper())
    if request.query_params.get('estado_movimiento'):
        movimientos = movimientos.filter(estado=request.query_params['estado_movimiento'].upper())
    if request.query_params.get('id_metodo_pago'):
        movimientos = movimientos.filter(id_metodo_pago_id=request.query_params['id_metodo_pago'])

    headers = ['Caja', 'Fecha', 'Tipo', 'Naturaleza', 'Metodo', 'Monto', 'Estado', 'Descripcion']
    keys = ['caja', 'fecha', 'tipo', 'naturaleza', 'metodo', 'monto', 'estado', 'descripcion']
    rows = [[
        m.caja_id,
        m.fecha.strftime('%Y-%m-%d %H:%M'),
        m.tipo_movimiento,
        m.naturaleza,
        m.id_metodo_pago.nombre if m.id_metodo_pago else '',
        m.monto,
        m.estado,
        m.descripcion,
    ] for m in movimientos]
    return headers, keys, rows


def _inventario_data(request):
    productos = Producto.consultar()
    if request.query_params.get('id_producto'):
        productos = productos.filter(pk=request.query_params['id_producto'])
    if request.query_params.get('id_categoria_producto'):
        productos = productos.filter(id_categoria_id=request.query_params['id_categoria_producto'])
    if request.query_params.get('id_marca'):
        productos = productos.filter(id_marca_id=request.query_params['id_marca'])
    if request.query_params.get('tipo_producto'):
        productos = productos.filter(tipo_producto=request.query_params['tipo_producto'].upper())
    if request.query_params.get('estado_producto'):
        productos = productos.filter(estado=request.query_params['estado_producto'].upper())
    stock_bajo = parse_bool(request.query_params.get('stock_bajo'))
    if stock_bajo is not None:
        productos = productos.filter(cantidad_disponible__lte=models.F('stock_minimo')) if stock_bajo else productos.filter(cantidad_disponible__gt=models.F('stock_minimo'))
    sin_stock = parse_bool(request.query_params.get('sin_stock'))
    if sin_stock is not None:
        productos = productos.filter(cantidad_disponible=0) if sin_stock else productos.exclude(cantidad_disponible=0)

    headers = ['ID', 'Producto', 'Categoria', 'Marca', 'Tipo', 'Stock', 'Stock minimo', 'Precio', 'Estado']
    keys = ['id', 'producto', 'categoria', 'marca', 'tipo', 'stock', 'stock_minimo', 'precio', 'estado']
    rows = [[
        p.id_producto,
        p.nombre,
        p.id_categoria.nombre,
        p.id_marca.nombre if p.id_marca else '',
        p.tipo_producto,
        p.cantidad_disponible,
        p.stock_minimo,
        p.precio_venta,
        p.estado,
    ] for p in productos]
    return headers, keys, rows


def _comisiones_data(request):
    comisiones = ComisionVenta.objects.select_related(
        'id_venta',
        'id_detalle',
        'id_detalle__id_servicio',
        'codigo_barbero',
    )
    comisiones = _fecha_rango(comisiones, request, 'id_venta__fecha_registro')
    if request.query_params.get('estado_venta'):
        comisiones = comisiones.filter(id_venta__estado=request.query_params['estado_venta'].upper())
    if request.query_params.get('barbero'):
        comisiones = comisiones.filter(codigo_barbero_id=request.query_params['barbero'])
    if request.query_params.get('id_servicio'):
        comisiones = comisiones.filter(id_detalle__id_servicio_id=request.query_params['id_servicio'])

    headers = ['Venta', 'Fecha', 'Barbero', 'Servicio', 'Porcentaje', 'Monto', 'Estado pago']
    keys = ['venta', 'fecha', 'barbero', 'servicio', 'porcentaje', 'monto', 'estado_pago']
    rows = [[
        c.id_venta_id,
        c.id_venta.fecha_registro.strftime('%Y-%m-%d %H:%M'),
        c.codigo_barbero_id,
        c.id_detalle.id_servicio.nombre if c.id_detalle.id_servicio else '',
        c.porcentaje,
        c.monto,
        c.estado_pago,
    ] for c in comisiones]
    return headers, keys, rows


def _servicios_promocion_data(request):
    detalles = DetallePromocion.objects.select_related(
        'id_promocion',
        'id_servicio',
        'id_servicio__id_categoria',
    )
    if request.query_params.get('id_promocion'):
        detalles = detalles.filter(id_promocion_id=request.query_params['id_promocion'])
    if request.query_params.get('id_servicio'):
        detalles = detalles.filter(id_servicio_id=request.query_params['id_servicio'])
    if request.query_params.get('id_categoria_servicio'):
        detalles = detalles.filter(id_servicio__id_categoria_id=request.query_params['id_categoria_servicio'])
    if request.query_params.get('estado_promocion'):
        detalles = detalles.filter(id_promocion__estado=request.query_params['estado_promocion'].upper())
    if request.query_params.get('tipo_descuento'):
        detalles = detalles.filter(id_promocion__tipo_descuento=request.query_params['tipo_descuento'].upper())
    fecha_inicio = parse_date(request.query_params.get('fecha_inicio'))
    fecha_fin = parse_date(request.query_params.get('fecha_fin'))
    if fecha_inicio:
        detalles = detalles.filter(id_promocion__fecha_fin__gte=fecha_inicio)
    if fecha_fin:
        detalles = detalles.filter(id_promocion__fecha_inicio__lte=fecha_fin)

    headers = ['Promocion', 'Estado', 'Tipo descuento', 'Valor', 'Inicio', 'Fin', 'Servicio', 'Categoria']
    keys = ['promocion', 'estado', 'tipo_descuento', 'valor', 'inicio', 'fin', 'servicio', 'categoria']
    rows = [[
        d.id_promocion.nombre,
        d.id_promocion.estado,
        d.id_promocion.tipo_descuento,
        d.id_promocion.valor_descuento,
        d.id_promocion.fecha_inicio,
        d.id_promocion.fecha_fin,
        d.id_servicio.nombre,
        d.id_servicio.id_categoria.nombre,
    ] for d in detalles]
    return headers, keys, rows

#caso de uso 19 generar reportes 
@extend_schema(tags=['CU21 - Reportes'], parameters=_common_report_params())
class ReporteVentasView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _ventas_data(request)
        registrar_bitacora(request, 'REPORTE_VENTAS', 'Descarga de reporte de ventas.')
        return report_response('Reporte de ventas', headers, rows, request.query_params.get('formato'), 'reporte-ventas')

#caso de uso 19
@extend_schema(tags=['CU21 - Reportes'], parameters=_common_report_params())
class ReporteProductosVendidosView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _productos_vendidos_data(request)
        registrar_bitacora(request, 'REPORTE_PRODUCTOS_VENDIDOS', 'Descarga de reporte de productos vendidos.')
        return report_response('Reporte de productos vendidos', headers, rows, request.query_params.get('formato'), 'productos-vendidos')


@extend_schema(tags=['CU21 - Reportes'], parameters=_common_report_params())
class ReporteServiciosRealizadosView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _servicios_realizados_data(request)
        registrar_bitacora(request, 'REPORTE_SERVICIOS_REALIZADOS', 'Descarga de reporte de servicios realizados.')
        return report_response('Reporte de servicios realizados', headers, rows, request.query_params.get('formato'), 'servicios-realizados')


@extend_schema(tags=['CU21 - Reportes'], parameters=_common_report_params())
class ReporteCajaMovimientosView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _caja_movimientos_data(request)
        registrar_bitacora(request, 'REPORTE_CAJA_MOVIMIENTOS', 'Descarga de reporte de caja y movimientos.')
        return report_response('Reporte de caja y movimientos', headers, rows, request.query_params.get('formato'), 'caja-movimientos')


@extend_schema(tags=['CU21 - Reportes'])
class ReporteInventarioView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _inventario_data(request)
        registrar_bitacora(request, 'REPORTE_INVENTARIO', 'Descarga de reporte de inventario.')
        return report_response('Reporte de inventario', headers, rows, request.query_params.get('formato'), 'inventario')


@extend_schema(tags=['CU21 - Reportes'], parameters=_common_report_params())
class ReporteComisionesView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _comisiones_data(request)
        registrar_bitacora(request, 'REPORTE_COMISIONES', 'Descarga de reporte de comisiones.')
        return report_response('Reporte de comisiones', headers, rows, request.query_params.get('formato'), 'comisiones')


@extend_schema(tags=['CU21 - Reportes'], parameters=_common_report_params())
class ReporteServiciosPromocionView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, _, rows = _servicios_promocion_data(request)
        registrar_bitacora(request, 'REPORTE_SERVICIOS_PROMOCION', 'Descarga de reporte de servicios con promocion.')
        return report_response('Reporte de servicios con promocion', headers, rows, request.query_params.get('formato'), 'servicios-promocion')


@extend_schema(tags=['CU21 - Reportes'])
class ReporteVentasPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _ventas_data(request)
        return _preview_response(headers, keys, rows)


@extend_schema(tags=['CU21 - Reportes'])
class ReporteProductosVendidosPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _productos_vendidos_data(request)
        return _preview_response(headers, keys, rows)


@extend_schema(tags=['CU21 - Reportes'])
class ReporteServiciosRealizadosPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _servicios_realizados_data(request)
        return _preview_response(headers, keys, rows)


@extend_schema(tags=['CU21 - Reportes'])
class ReporteCajaMovimientosPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _caja_movimientos_data(request)
        return _preview_response(headers, keys, rows)


@extend_schema(tags=['CU21 - Reportes'])
class ReporteInventarioPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _inventario_data(request)
        return _preview_response(headers, keys, rows)


@extend_schema(tags=['CU21 - Reportes'])
class ReporteComisionesPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _comisiones_data(request)
        return _preview_response(headers, keys, rows)


@extend_schema(tags=['CU21 - Reportes'])
class ReporteServiciosPromocionPreviewView(APIView):
    permission_classes = [EsAdmin]

    def get(self, request):
        headers, keys, rows = _servicios_promocion_data(request)
        return _preview_response(headers, keys, rows)
