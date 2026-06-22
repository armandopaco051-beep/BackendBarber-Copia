from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify

from apps.reportes.utils import build_pdf


def _nombre_persona(usuario, fallback='-'):
    if not usuario:
        return fallback
    nombre = f'{usuario.nombre} {usuario.apellido}'.strip()
    return nombre or usuario.codigo


def _detalle_nombre(detalle):
    if detalle.tipo_item == 'PRODUCTO':
        return detalle.id_producto.nombre if detalle.id_producto else 'Producto'
    return detalle.id_servicio.nombre if detalle.id_servicio else 'Servicio'


def _decimal(value):
    return f'{value:.2f}'


def comprobante_venta_pdf(venta):
    generado = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    fecha_venta = timezone.localtime(venta.fecha_registro).strftime('%Y-%m-%d %H:%M')
    cliente = _nombre_persona(venta.codigo_cliente, 'Consumidor final')
    cajero = _nombre_persona(venta.codigo_cajero)

    headers = ['Concepto', 'Detalle']
    rows = [
        ['Comprobante', f'COMP-{venta.id_venta:06d}'],
        ['Venta', f'#{venta.id_venta}'],
        ['Fecha venta', fecha_venta],
        ['Generado', generado],
        ['Cliente', cliente],
        ['Cajero', cajero],
        ['Estado', venta.estado],
        ['', ''],
        ['Items', 'Cantidad | Precio | Descuento | Subtotal'],
    ]

    for detalle in venta.detalles.all():
        rows.append([
            _detalle_nombre(detalle),
            (
                f'{detalle.cantidad} x Bs. {_decimal(detalle.precio_unitario)} | '
                f'Desc. Bs. {_decimal(detalle.descuento)} | '
                f'Bs. {_decimal(detalle.subtotal)}'
            ),
        ])

    rows.extend([
        ['', ''],
        ['Subtotal', f'Bs. {_decimal(venta.subtotal)}'],
        ['Descuento', f'Bs. {_decimal(venta.descuento)}'],
        ['Total pagado', f'Bs. {_decimal(venta.total)}'],
        ['', ''],
        ['Pagos', 'Metodo | Monto | Referencia'],
    ])

    for pago in venta.pagos.all():
        referencia = pago.referencia or 'Sin referencia'
        rows.append([
            pago.id_metodo_pago.nombre,
            f'Bs. {_decimal(pago.monto)} | {referencia}',
        ])

    rows.extend([
        ['', ''],
        ['Observacion', venta.observacion or 'Sin observacion'],
        ['Mensaje', 'Gracias por su preferencia.'],
    ])

    contenido = build_pdf('Blessed Barber Club - Comprobante de pago', headers, rows)
    filename = slugify(f'comprobante-venta-{venta.id_venta}') or f'comprobante-{venta.id_venta}'
    response = HttpResponse(contenido, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    return response
