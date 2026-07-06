from decimal import Decimal
import hashlib
import hmac
import json
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.citas.models import AtencionServicio, EstadoCita, HistorialEstadoCita, Cita
from apps.inventario.models import MovimientoInventario, Producto
from apps.seguridad.models import Usuario
from apps.servicios.models import Servicio

from .models import (
    Caja,
    ComisionVenta,
    DetalleVenta,
    MetodoPago,
    MovimientoCaja,
    PagoStripe,
    PagoVenta,
    PlanComision,
    Venta,
    VentaCuotas,
    CuotaVenta,
)


STRIPE_API_BASE = 'https://api.stripe.com/v1'


def _obtener_usuario(codigo, campo):
    try:
        return Usuario.objects.select_related('id_rol').get(pk=codigo)
    except Usuario.DoesNotExist:
        raise ValidationError({campo: 'Usuario no encontrado.'})


def _decimal_a_minor_units(monto):
    return int((monto * Decimal('100')).quantize(Decimal('1')))


def _obtener_metodo_pago_stripe():
    metodo = MetodoPago.objects.filter(nombre__iexact='Stripe').first()
    if not metodo:
        metodo = MetodoPago.objects.create(
            nombre='Stripe',
            descripcion='Pago con tarjeta mediante Stripe',
            requiere_referencia=True,
            estado='ACTIVO',
        )
    if metodo.estado != 'ACTIVO':
        metodo.estado = 'ACTIVO'
        metodo.save(update_fields=['estado', 'fecha_actualizacion'])
    if not metodo.requiere_referencia:
        metodo.requiere_referencia = True
        metodo.save(update_fields=['requiere_referencia', 'fecha_actualizacion'])
    return metodo


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


def _registrar_salida_productos(venta, usuario):
    for detalle in venta.detalles.select_related('id_producto'):
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


def _registrar_comisiones_venta(venta):
    venta.comisiones.all().delete()
    for detalle in venta.detalles.select_related('codigo_barbero'):
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
            atencion = AtencionServicio.objects.filter(
                id_cita=cita,
                estado='FINALIZADA',
                listo_para_cobro=True,
            ).prefetch_related('detalles__id_servicio').first()
            detalles_atencion = list(atencion.detalles.select_related('id_servicio').all()) if atencion else []
            if detalles_atencion:
                detalles = [
                    {
                        'tipo_item': 'SERVICIO',
                        'id_servicio': detalle.id_servicio_id,
                        'codigo_barbero': atencion.codigo_barbero_id,
                        'cantidad': detalle.cantidad,
                        'descuento': Decimal('0.00'),
                    }
                    for detalle in detalles_atencion
                ] + detalles
            else:
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


def _generar_cuotas(venta_cuotas, saldo, cantidad_cuotas, fecha_primer_vencimiento, dias_entre_cuotas):
    # CU33: divide el saldo pendiente en cuotas y ajusta la ultima para evitar diferencias por redondeo.
    monto_base = (saldo / Decimal(cantidad_cuotas)).quantize(Decimal('0.01'))
    cuotas = []
    acumulado = Decimal('0.00')

    for numero in range(1, cantidad_cuotas + 1):
        if numero == cantidad_cuotas:
            monto = saldo - acumulado
        else:
            monto = monto_base
            acumulado += monto

        cuotas.append(CuotaVenta(
            id_venta_cuotas=venta_cuotas,
            numero_cuota=numero,
            monto=monto,
            fecha_vencimiento=fecha_primer_vencimiento + timedelta(days=dias_entre_cuotas * (numero - 1)),
            estado='PENDIENTE',
        ))

    CuotaVenta.objects.bulk_create(cuotas)


@transaction.atomic
def registrar_venta_por_cuotas(data, usuario):
    # CU33: orquesta todo el registro de una venta financiada dentro de una transaccion.
    if not usuario:
        raise ValidationError('No se pudo identificar al usuario actual.')

    # Precondicion: debe existir una caja abierta para registrar el monto inicial recibido.
    caja = _validar_caja_abierta()

    # Precondicion: el pago inicial necesita un metodo de pago activo y su referencia si aplica.
    metodo = MetodoPago.objects.filter(pk=data['id_metodo_pago_inicial'], estado='ACTIVO').first()
    if not metodo:
        raise ValidationError({'id_metodo_pago_inicial': 'Metodo de pago no encontrado o inactivo.'})

    referencia = (data.get('referencia_inicial') or '').strip()
    if metodo.requiere_referencia and not referencia:
        raise ValidationError({'referencia_inicial': f'El metodo {metodo.nombre} requiere referencia.'})

    # Crea la venta base usando el mismo flujo de detalle de productos/servicios de ventas normales.
    venta_data = {
        'codigo_cliente': data.get('codigo_cliente'),
        'id_cita': data.get('id_cita'),
        'descuento': data.get('descuento') or Decimal('0.00'),
        'observacion': data.get('observacion') or 'Venta por cuotas',
        'detalles': data.get('detalles') or [],
    }
    venta = crear_venta_borrador(venta_data, usuario)
    venta = Venta.objects.select_for_update().prefetch_related('detalles').get(pk=venta.pk)
    venta.recalcular_totales()

    # Valida reglas propias de cuotas: cliente obligatorio, total valido e inicial menor al total.
    if not venta.codigo_cliente_id:
        raise ValidationError({'codigo_cliente': 'Debe existir un cliente asociado a la venta.'})
    if venta.total <= 0:
        raise ValidationError({'total': 'El total de la venta debe ser mayor a 0.'})

    monto_inicial = data['monto_inicial']
    if monto_inicial >= venta.total:
        raise ValidationError({'monto_inicial': 'El monto inicial debe ser menor al total de la venta.'})

    cantidad_cuotas = data['cantidad_cuotas']
    if cantidad_cuotas <= 0:
        raise ValidationError({'cantidad_cuotas': 'La cantidad de cuotas debe ser mayor a 0.'})

    saldo_pendiente = venta.total - monto_inicial

    # Registra el pago inicial y el movimiento de caja correspondiente.
    pago = PagoVenta.objects.create(
        id_venta=venta,
        id_metodo_pago=metodo,
        monto=monto_inicial,
        referencia=referencia,
    )
    _crear_movimiento_caja(
        caja=caja,
        usuario=usuario,
        tipo_movimiento='VENTA',
        monto=monto_inicial,
        descripcion=f'Pago inicial venta por cuotas #{venta.id_venta}',
        metodo_pago=metodo,
        referencia=referencia or f'CUOTAS-{venta.id_venta}',
        venta=venta,
        pago_venta=pago,
    )

    # Aplica efectos de la venta confirmada: salida de inventario y comisiones.
    _registrar_salida_productos(venta, usuario)
    _registrar_comisiones_venta(venta)

    # La venta queda pendiente de pago porque aun existen cuotas por cobrar.
    venta.estado = 'PENDIENTE_PAGO'
    venta.save(update_fields=['estado', 'fecha_actualizacion'])

    # Crea el plan de cuotas y su detalle de vencimientos.
    venta_cuotas = VentaCuotas.objects.create(
        id_venta=venta,
        monto_inicial=monto_inicial,
        saldo_pendiente=saldo_pendiente,
        cantidad_cuotas=cantidad_cuotas,
        estado='PENDIENTE',
    )
    _generar_cuotas(
        venta_cuotas=venta_cuotas,
        saldo=saldo_pendiente,
        cantidad_cuotas=cantidad_cuotas,
        fecha_primer_vencimiento=data['fecha_primer_vencimiento'],
        dias_entre_cuotas=data.get('dias_entre_cuotas') or 30,
    )

    # Actualiza el saldo esperado de caja con el monto inicial registrado.
    caja.recalcular_saldo_esperado()
    return VentaCuotas.consultar().get(pk=venta_cuotas.pk)


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
def crear_payment_intent_stripe(venta_id, usuario):
    secret_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    currency = getattr(settings, 'STRIPE_CURRENCY', 'bob').lower()
    if not secret_key:
        raise ValidationError({'stripe': 'STRIPE_SECRET_KEY no esta configurado.'})

    venta = Venta.objects.select_for_update().get(pk=venta_id)
    if venta.estado not in ['BORRADOR', 'PENDIENTE_PAGO']:
        raise ValidationError('Solo se puede crear pago Stripe para ventas en borrador o pendientes de pago.')

    detalles = list(venta.detalles.all())
    if not detalles:
        raise ValidationError('No se puede cobrar una venta sin detalles.')

    if not Caja.caja_abierta():
        raise ValidationError('Debe existir una caja abierta antes de iniciar un pago con Stripe.')

    venta.recalcular_totales()
    if venta.total <= 0:
        raise ValidationError('El total de la venta debe ser mayor a 0.')

    amount = _decimal_a_minor_units(venta.total)
    data = {
        'amount': amount,
        'currency': currency,
        'automatic_payment_methods[enabled]': 'true',
        'metadata[id_venta]': str(venta.id_venta),
        'metadata[codigo_cajero]': usuario.codigo if usuario else '',
        'description': f'Venta #{venta.id_venta} - Blessed Barber',
    }
    idempotency_key = f'venta-{venta.id_venta}-stripe-{amount}-{currency}'

    try:
        response = requests.post(
            f'{STRIPE_API_BASE}/payment_intents',
            data=data,
            auth=(secret_key, ''),
            headers={'Idempotency-Key': idempotency_key},
            timeout=20,
        )
    except requests.RequestException:
        raise ValidationError({'stripe': 'No se pudo conectar con Stripe.'})

    try:
        stripe_data = response.json()
    except ValueError:
        stripe_data = {}

    if response.status_code >= 400:
        mensaje = stripe_data.get('error', {}).get('message') or 'Stripe rechazo la solicitud.'
        raise ValidationError({'stripe': mensaje})

    pago_stripe, _ = PagoStripe.objects.update_or_create(
        stripe_payment_intent_id=stripe_data['id'],
        defaults={
            'id_venta': venta,
            'client_secret': stripe_data.get('client_secret', ''),
            'stripe_status': stripe_data.get('status', ''),
            'estado': 'REQUIERE_PAGO',
            'amount': stripe_data.get('amount', amount),
            'currency': stripe_data.get('currency', currency),
            'raw_response': stripe_data,
        },
    )

    if venta.estado != 'PENDIENTE_PAGO':
        venta.estado = 'PENDIENTE_PAGO'
        venta.save(update_fields=['estado', 'fecha_actualizacion'])

    return pago_stripe


def verificar_firma_stripe(payload, signature_header):
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    if not webhook_secret:
        raise ValidationError({'stripe': 'STRIPE_WEBHOOK_SECRET no esta configurado.'})
    if not signature_header:
        raise ValidationError({'stripe': 'Falta Stripe-Signature.'})

    partes = {}
    for item in signature_header.split(','):
        if '=' not in item:
            continue
        key, value = item.split('=', 1)
        partes.setdefault(key, []).append(value)

    timestamp = partes.get('t', [None])[0]
    firmas = partes.get('v1', [])
    if not timestamp or not firmas:
        raise ValidationError({'stripe': 'Firma Stripe invalida.'})

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        raise ValidationError({'stripe': 'Timestamp Stripe invalido.'})

    if abs(time.time() - timestamp_int) > 300:
        raise ValidationError({'stripe': 'Firma Stripe expirada.'})

    signed_payload = f'{timestamp}.'.encode('utf-8') + payload
    expected = hmac.new(webhook_secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, firma) for firma in firmas):
        raise ValidationError({'stripe': 'Firma Stripe no coincide.'})


@transaction.atomic
def procesar_webhook_stripe(payload, signature_header):
    verificar_firma_stripe(payload, signature_header)

    try:
        event = json.loads(payload.decode('utf-8'))
    except ValueError:
        raise ValidationError({'stripe': 'Payload Stripe invalido.'})

    event_type = event.get('type')
    payment_intent = event.get('data', {}).get('object', {})
    payment_intent_id = payment_intent.get('id')
    if not payment_intent_id:
        return {'procesado': False, 'motivo': 'Evento sin PaymentIntent.'}

    pago_stripe = PagoStripe.objects.select_for_update().select_related('id_venta', 'id_venta__codigo_cajero').filter(
        stripe_payment_intent_id=payment_intent_id
    ).first()
    if not pago_stripe:
        return {'procesado': False, 'motivo': 'PaymentIntent no vinculado a una venta.'}

    pago_stripe.stripe_status = payment_intent.get('status', pago_stripe.stripe_status)
    pago_stripe.raw_response = payment_intent

    if event_type == 'payment_intent.succeeded':
        if pago_stripe.id_venta.estado != 'PAGADA':
            metodo = _obtener_metodo_pago_stripe()
            monto = Decimal(pago_stripe.amount) / Decimal('100')
            confirmar_venta(
                pago_stripe.id_venta_id,
                [{
                    'id_metodo_pago': metodo.id_metodo_pago,
                    'monto': monto,
                    'referencia': payment_intent_id,
                }],
                pago_stripe.id_venta.codigo_cajero,
            )
        pago_stripe.estado = 'EXITOSO'
        pago_stripe.fecha_confirmacion = timezone.now()
    elif event_type == 'payment_intent.payment_failed':
        pago_stripe.estado = 'FALLIDO'
    elif event_type == 'payment_intent.canceled':
        pago_stripe.estado = 'CANCELADO'
    elif event_type == 'payment_intent.processing':
        pago_stripe.estado = 'PROCESANDO'

    pago_stripe.save(update_fields=[
        'stripe_status',
        'estado',
        'raw_response',
        'fecha_confirmacion',
        'fecha_actualizacion',
    ])
    return {'procesado': True, 'evento': event_type, 'payment_intent_id': payment_intent_id}


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
