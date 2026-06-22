from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.citas.models import EstadoCita, HistorialEstadoCita, Cita
from apps.inventario.models import MovimientoInventario, Producto
from apps.seguridad.models import Usuario
from apps.servicios.models import Servicio

from .models import (
    Caja,
    ComisionVenta,
    DetalleVenta,
    MetodoPago,
    MovimientoCaja,
    PagoVenta,
    PlanComision,
    Venta,
)


def _obtener_usuario(codigo, campo):
    try:
        return Usuario.objects.select_related('id_rol').get(pk=codigo)
    except Usuario.DoesNotExist:
        raise ValidationError({campo: 'Usuario no encontrado.'})


def _naturaleza_por_tipo(tipo_movimiento):
    if tipo_movimiento in ['INGRESO_MANUAL', 'VENTA', 'AJUSTE_POSITIVO']:
        return 'INGRESO'
    return 'EGRESO'


def _metodo_efectivo():
    return MetodoPago.objects.filter(nombre__iexact='EFECTIVO', estado='ACTIVO').first()


def _validar_caja_abierta():
    caja = Caja.caja_abierta()
    if not caja:
        raise ValidationError('Debe existir una caja abierta.')
    return caja


def _crear_movimiento_caja(
    caja,
    usuario,
    tipo_movimiento,
    monto,
    descripcion,
    metodo_pago=None,
    referencia='',
    venta=None,
    pago_venta=None,
):
    naturaleza = _naturaleza_por_tipo(tipo_movimiento)
    return MovimientoCaja.objects.create(
        caja=caja,
        tipo=naturaleza,
        tipo_movimiento=tipo_movimiento,
        naturaleza=naturaleza,
        id_metodo_pago=metodo_pago,
        id_venta=venta,
        id_pago_venta=pago_venta,
        monto=monto,
        descripcion=descripcion,
        referencia=referencia,
        usuario=usuario,
    )


@transaction.atomic
def registrar_movimiento_caja_manual(data, usuario):
    if not usuario:
        raise ValidationError('No se pudo identificar al usuario actual.')

    caja = _validar_caja_abierta()
    tipo_movimiento = data['tipo_movimiento']
    monto = data['monto']
    descripcion = data['descripcion']
    referencia = (data.get('referencia') or '').strip()

    metodo = None
    if data.get('id_metodo_pago'):
        try:
            metodo = MetodoPago.objects.get(pk=data['id_metodo_pago'], estado='ACTIVO')
        except MetodoPago.DoesNotExist:
            raise ValidationError({'id_metodo_pago': 'Metodo de pago no encontrado o inactivo.'})
    else:
        metodo = _metodo_efectivo()

    if tipo_movimiento in ['EGRESO', 'RETIRO', 'AJUSTE_NEGATIVO'] and metodo and metodo.nombre.upper() == 'EFECTIVO':
        if caja.saldo_efectivo < monto:
            raise ValidationError({'monto': 'Saldo efectivo insuficiente para registrar el movimiento.'})

    movimiento = _crear_movimiento_caja(
        caja=caja,
        usuario=usuario,
        tipo_movimiento=tipo_movimiento,
        monto=monto,
        descripcion=descripcion,
        metodo_pago=metodo,
        referencia=referencia,
    )
    caja.recalcular_saldo_esperado()
    return movimiento


@transaction.atomic
def anular_movimiento_caja(id_movimiento_caja, motivo, usuario):
    movimiento = MovimientoCaja.objects.select_for_update().get(pk=id_movimiento_caja)
    if movimiento.caja.estado != 'ABIERTA':
        raise ValidationError('Solo se pueden anular movimientos de una caja abierta.')
    if movimiento.estado == 'ANULADO':
        raise ValidationError('El movimiento ya se encuentra anulado.')
    if movimiento.tipo_movimiento in ['VENTA', 'DEVOLUCION']:
        raise ValidationError('Los movimientos generados por ventas se anulan desde la venta.')

    movimiento.estado = 'ANULADO'
    movimiento.motivo_anulacion = motivo
    movimiento.save(update_fields=['estado', 'motivo_anulacion'])
    movimiento.caja.recalcular_saldo_esperado()
    return movimiento


def resumen_caja_abierta():
    caja = _validar_caja_abierta()
    movimientos = caja.movimientos.filter(estado='ACTIVO')
    resumen_metodos = []

    for metodo in MetodoPago.objects.all().order_by('nombre'):
        ingresos = movimientos.filter(
            tipo='INGRESO',
            id_metodo_pago=metodo,
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        egresos = movimientos.filter(
            tipo='EGRESO',
            id_metodo_pago=metodo,
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        if ingresos or egresos:
            resumen_metodos.append({
                'id_metodo_pago': metodo.id_metodo_pago,
                'metodo_pago': metodo.nombre,
                'ingresos': ingresos,
                'egresos': egresos,
                'saldo': ingresos - egresos,
            })

    return {
        'caja_id': caja.id_caja,
        'estado': caja.estado,
        'monto_apertura': caja.monto_apertura,
        'ingresos': caja.ingresos,
        'egresos': caja.egresos,
        'saldo_actual': caja.saldo_actual,
        'saldo_efectivo': caja.saldo_efectivo,
        'resumen_metodos_pago': resumen_metodos,
    }


def _crear_detalle(venta, item):
    tipo_item = item['tipo_item']
    cantidad = item.get('cantidad') or 1
    descuento = item.get('descuento') or Decimal('0.00')

    if tipo_item == 'PRODUCTO':
        try:
            producto = Producto.objects.get(pk=item['id_producto'])
        except Producto.DoesNotExist:
            raise ValidationError({'id_producto': 'Producto no encontrado.'})

        if producto.estado != 'ACTIVO':
            raise ValidationError({'id_producto': 'El producto debe estar activo.'})
        if producto.tipo_producto not in ['VENTA', 'AMBOS']:
            raise ValidationError({'id_producto': 'El producto no esta habilitado para venta.'})
        if producto.cantidad_disponible < cantidad:
            raise ValidationError({'cantidad': f'Stock insuficiente para {producto.nombre}.'})

        precio_unitario = producto.precio_venta
        subtotal = (precio_unitario * cantidad) - descuento
        if subtotal < 0:
            raise ValidationError({'descuento': 'El descuento del detalle no puede superar su subtotal.'})

        return DetalleVenta.objects.create(
            id_venta=venta,
            tipo_item='PRODUCTO',
            id_producto=producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            descuento=descuento,
            subtotal=subtotal,
        )

    try:
        servicio = Servicio.objects.get(pk=item['id_servicio'])
    except Servicio.DoesNotExist:
        raise ValidationError({'id_servicio': 'Servicio no encontrado.'})

    if servicio.estado != 'ACTIVO':
        raise ValidationError({'id_servicio': 'El servicio debe estar activo.'})

    barbero = _obtener_usuario(item['codigo_barbero'], 'codigo_barbero')
    if not barbero.es_barbero:
        raise ValidationError({'codigo_barbero': 'El usuario seleccionado debe tener rol Barbero.'})

    precio_unitario = servicio.precio
    subtotal = (precio_unitario * cantidad) - descuento
    if subtotal < 0:
        raise ValidationError({'descuento': 'El descuento del detalle no puede superar su subtotal.'})

    return DetalleVenta.objects.create(
        id_venta=venta,
        tipo_item='SERVICIO',
        id_servicio=servicio,
        codigo_barbero=barbero,
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        descuento=descuento,
        subtotal=subtotal,
    )


@transaction.atomic
def crear_venta_borrador(data, usuario):
    if not usuario:
        raise ValidationError('No se pudo identificar al usuario actual.')

    cliente = None
    if data.get('codigo_cliente'):
        cliente = _obtener_usuario(data['codigo_cliente'], 'codigo_cliente')

    cita = None
    if data.get('id_cita'):
        try:
            cita = Cita.objects.select_related('codigo_cliente', 'codigo_barbero').prefetch_related(
                'servicios_detalle__id_servicio'
            ).get(pk=data['id_cita'])
        except Cita.DoesNotExist:
            raise ValidationError({'id_cita': 'Cita no encontrada.'})
        if not cliente:
            cliente = cita.codigo_cliente

    venta = Venta.objects.create(
        codigo_cliente=cliente,
        id_cita=cita,
        codigo_cajero=usuario,
        descuento=data.get('descuento') or Decimal('0.00'),
        observacion=(data.get('observacion') or '').strip(),
    )

    detalles = list(data.get('detalles') or [])
    if cita:
        tiene_servicios_enviados = any(item.get('tipo_item') == 'SERVICIO' for item in detalles)
        if not tiene_servicios_enviados:
            detalles_cita = list(cita.servicios_detalle.select_related('id_servicio').all())
            if detalles_cita:
                detalles = [
                    {
                        'tipo_item': 'SERVICIO',
                        'id_servicio': detalle.id_servicio_id,
                        'codigo_barbero': cita.codigo_barbero_id,
                        'cantidad': 1,
                        'descuento': Decimal('0.00'),
                    }
                    for detalle in detalles_cita
                ] + detalles
            elif cita.id_servicio_id:
                detalles = [
                    {
                        'tipo_item': 'SERVICIO',
                        'id_servicio': cita.id_servicio_id,
                        'codigo_barbero': cita.codigo_barbero_id,
                        'cantidad': 1,
                        'descuento': Decimal('0.00'),
                    }
                ] + detalles

    if not detalles:
        raise ValidationError({'detalles': 'La venta debe tener al menos un detalle.'})

    for item in detalles:
        _crear_detalle(venta, item)

    venta.recalcular_totales()
    if venta.descuento > venta.subtotal:
        raise ValidationError({'descuento': 'El descuento de la venta no puede superar el subtotal.'})

    return venta


@transaction.atomic
def confirmar_venta(venta_id, pagos_data, usuario):
    venta = Venta.objects.select_for_update().get(pk=venta_id)
    if venta.estado not in ['BORRADOR', 'PENDIENTE_PAGO']:
        raise ValidationError('Solo se pueden confirmar ventas en borrador o pendientes de pago.')

    detalles = list(venta.detalles.select_related('id_producto', 'id_servicio', 'codigo_barbero'))
    if not detalles:
        raise ValidationError('No se puede confirmar una venta sin detalles.')

    venta.recalcular_totales()
    total_pagos = sum((pago['monto'] for pago in pagos_data), Decimal('0.00'))
    if total_pagos != venta.total:
        raise ValidationError({'pagos': 'La suma de pagos debe ser igual al total de la venta.'})

    caja = Caja.caja_abierta()
    if not caja:
        raise ValidationError('Debe existir una caja abierta para confirmar la venta.')

    venta.pagos.all().delete()
    for pago_data in pagos_data:
        try:
            metodo = MetodoPago.objects.get(pk=pago_data['id_metodo_pago'], estado='ACTIVO')
        except MetodoPago.DoesNotExist:
            raise ValidationError({'id_metodo_pago': 'Metodo de pago no encontrado o inactivo.'})

        referencia = (pago_data.get('referencia') or '').strip()
        if metodo.requiere_referencia and not referencia:
            raise ValidationError({'referencia': f'El metodo {metodo.nombre} requiere referencia.'})

        pago = PagoVenta.objects.create(
            id_venta=venta,
            id_metodo_pago=metodo,
            monto=pago_data['monto'],
            referencia=referencia,
        )
        _crear_movimiento_caja(
            caja=caja,
            usuario=usuario,
            tipo_movimiento='VENTA',
            monto=pago.monto,
            descripcion=f'Ingreso por venta #{venta.id_venta}',
            metodo_pago=metodo,
            referencia=referencia or f'VENTA-{venta.id_venta}',
            venta=venta,
            pago_venta=pago,
        )

    for detalle in detalles:
        if detalle.tipo_item != 'PRODUCTO':
            continue

        producto = Producto.objects.select_for_update().get(pk=detalle.id_producto_id)
        if producto.cantidad_disponible < detalle.cantidad:
            raise ValidationError({'stock': f'Stock insuficiente para {producto.nombre}.'})

        stock_anterior = producto.cantidad_disponible
        producto.cantidad_disponible = stock_anterior - detalle.cantidad
        producto.save(update_fields=['cantidad_disponible', 'fecha_actualizacion'])

        MovimientoInventario.objects.create(
            id_producto=producto,
            tipo_movimiento='SALIDA_VENTA',
            cantidad=detalle.cantidad,
            stock_anterior=stock_anterior,
            stock_nuevo=producto.cantidad_disponible,
            motivo=f'Venta #{venta.id_venta}',
            id_venta=venta,
            usuario=usuario,
        )

    venta.comisiones.all().delete()
    for detalle in detalles:
        if detalle.tipo_item != 'SERVICIO' or not detalle.codigo_barbero_id:
            continue

        plan = PlanComision.objects.filter(
            codigo_barbero=detalle.codigo_barbero,
            estado='ACTIVO',
            fecha_inicio__lte=timezone.localdate(),
        ).order_by('-fecha_inicio').first()
        if not plan:
            continue

        porcentaje = plan.porcentaje_barbero
        monto = (detalle.subtotal * porcentaje) / Decimal('100')
        ComisionVenta.objects.create(
            id_venta=venta,
            id_detalle=detalle,
            codigo_barbero=detalle.codigo_barbero,
            porcentaje=porcentaje,
            monto=monto,
        )

    caja.recalcular_saldo_esperado()

    if venta.id_cita_id:
        estado_finalizada = EstadoCita.objects.filter(nombre__iexact='FINALIZADA').first()
        if estado_finalizada and venta.id_cita.id_estadoc_id != estado_finalizada.pk:
            estado_anterior = venta.id_cita.id_estadoc
            venta.id_cita.id_estadoc = estado_finalizada
            venta.id_cita.save(update_fields=['id_estadoc', 'fecha_actualizacion'])
            HistorialEstadoCita.objects.create(
                id_cita=venta.id_cita,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_finalizada,
                observacion=f'Finalizada por venta #{venta.id_venta}',
                cambiado_por=usuario,
            )

    venta.estado = 'PAGADA'
    venta.save(update_fields=['estado', 'fecha_actualizacion'])
    return venta


@transaction.atomic
def anular_venta(venta_id, motivo, usuario):
    venta = Venta.objects.select_for_update().get(pk=venta_id)
    if venta.estado == 'ANULADA':
        raise ValidationError('La venta ya se encuentra anulada.')

    if venta.estado == 'PAGADA':
        caja = Caja.caja_abierta()
        if not caja:
            raise ValidationError('Debe existir una caja abierta para anular una venta pagada.')

        for detalle in venta.detalles.select_related('id_producto'):
            if detalle.tipo_item != 'PRODUCTO':
                continue

            producto = Producto.objects.select_for_update().get(pk=detalle.id_producto_id)
            stock_anterior = producto.cantidad_disponible
            producto.cantidad_disponible = stock_anterior + detalle.cantidad
            producto.save(update_fields=['cantidad_disponible', 'fecha_actualizacion'])

            MovimientoInventario.objects.create(
                id_producto=producto,
                tipo_movimiento='DEVOLUCION',
                cantidad=detalle.cantidad,
                stock_anterior=stock_anterior,
                stock_nuevo=producto.cantidad_disponible,
                motivo=f'Anulacion de venta #{venta.id_venta}: {motivo}',
                id_venta=venta,
                usuario=usuario,
            )

        for pago in venta.pagos.select_related('id_metodo_pago').filter(estado='REGISTRADO'):
            _crear_movimiento_caja(
                caja=caja,
                usuario=usuario,
                tipo_movimiento='DEVOLUCION',
                monto=pago.monto,
                descripcion=f'Anulacion de venta #{venta.id_venta}: {motivo}',
                metodo_pago=pago.id_metodo_pago,
                referencia=pago.referencia or f'ANULA-VENTA-{venta.id_venta}',
                venta=venta,
                pago_venta=pago,
            )
        caja.recalcular_saldo_esperado()

    venta.pagos.update(estado='ANULADO')
    venta.comisiones.update(estado_pago='ANULADA')
    venta.estado = 'ANULADA'
    venta.motivo_anulacion = motivo
    venta.save(update_fields=['estado', 'motivo_anulacion', 'fecha_actualizacion'])
    return venta
