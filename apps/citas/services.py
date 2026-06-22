from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.servicios.models import Servicio

from .models import AtencionServicio, BarberoServicio, Cita, DetalleAtencionServicio, HistorialEstadoCita
from .serializers import obtener_estado_cita


ESTADOS_CITA_NO_ATENDIBLES = ['ANULADA', 'CANCELADA', 'FINALIZADA', 'ATENDIDA', 'NO_ASISTIO']


def _validar_barbero_atencion(cita, usuario):
    if not usuario:
        raise ValidationError('No se pudo identificar al usuario actual.')
    if usuario.es_admin:
        return
    if not usuario.es_barbero:
        raise ValidationError('Solo el barbero asignado o un administrador puede registrar la atencion.')
    if cita.codigo_barbero_id != usuario.codigo:
        raise ValidationError('Solo el barbero asignado puede registrar esta atencion.')


def _cambiar_estado_cita(cita, estado_nombre, usuario, observacion=''):
    estado_anterior = cita.id_estadoc
    estado_nuevo = obtener_estado_cita(estado_nombre)
    if cita.id_estadoc_id == estado_nuevo.id_estado:
        return cita

    cita.id_estadoc = estado_nuevo
    cita.save(update_fields=['id_estadoc', 'fecha_actualizacion'])
    HistorialEstadoCita.objects.create(
        id_cita=cita,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        observacion=observacion,
        cambiado_por=usuario,
    )
    return cita


def _copiar_servicios_cita(atencion):
    cita = atencion.id_cita
    detalles_cita = list(cita.servicios_detalle.select_related('id_servicio').all())
    servicios = []
    if detalles_cita:
        servicios = [
            {
                'servicio': detalle.id_servicio,
                'precio': detalle.precio_unitario,
                'cantidad': 1,
                'observacion': 'Servicio reservado',
            }
            for detalle in detalles_cita
        ]
    elif cita.id_servicio_id:
        servicios = [{
            'servicio': cita.id_servicio,
            'precio': cita.id_servicio.precio,
            'cantidad': 1,
            'observacion': 'Servicio reservado',
        }]

    DetalleAtencionServicio.objects.bulk_create([
        DetalleAtencionServicio(
            id_atencion=atencion,
            id_servicio=item['servicio'],
            precio_unitario=item['precio'],
            cantidad=item['cantidad'],
            subtotal=item['precio'] * item['cantidad'],
            observacion=item['observacion'],
        )
        for item in servicios
    ], ignore_conflicts=True)
    atencion.recalcular_total()


def _validar_servicios_habilitados(barbero, servicios):
    asignaciones = BarberoServicio.objects.filter(codigo_barbero=barbero)
    if not asignaciones.exists():
        return
    no_habilitados = [
        servicio.nombre
        for servicio in servicios
        if not asignaciones.filter(id_servicio=servicio, estado='ACTIVO').exists()
    ]
    if no_habilitados:
        raise ValidationError({'servicios': f"El barbero no esta habilitado para: {', '.join(no_habilitados)}."})


@transaction.atomic
def iniciar_atencion(id_cita, usuario):
    try:
        cita = Cita.objects.select_for_update().select_related(
            'codigo_cliente',
            'codigo_barbero',
            'id_servicio',
            'id_estadoc',
        ).prefetch_related('servicios_detalle__id_servicio').get(pk=id_cita)
    except Cita.DoesNotExist:
        raise ValidationError({'id_cita': 'Cita no encontrada.'})

    _validar_barbero_atencion(cita, usuario)
    estado_cita = cita.id_estadoc.nombre.upper()
    if estado_cita in ESTADOS_CITA_NO_ATENDIBLES:
        raise ValidationError({'id_cita': f'No se puede iniciar una cita en estado {estado_cita}.'})

    atencion, creada = AtencionServicio.objects.select_for_update().get_or_create(
        id_cita=cita,
        defaults={
            'codigo_barbero': cita.codigo_barbero,
            'codigo_cliente': cita.codigo_cliente,
            'fecha': cita.fecha,
            'estado': 'EN_ATENCION',
            'hora_inicio': timezone.now(),
            'registrado_por': usuario,
        },
    )

    if not creada:
        if atencion.estado == 'FINALIZADA':
            raise ValidationError('La atencion ya fue finalizada.')
        if atencion.estado in ['CANCELADA', 'NO_ASISTIO']:
            raise ValidationError(f'La atencion esta en estado {atencion.estado}.')
        if atencion.estado == 'PENDIENTE':
            atencion.estado = 'EN_ATENCION'
            atencion.hora_inicio = timezone.now()
            atencion.registrado_por = usuario
            atencion.save(update_fields=['estado', 'hora_inicio', 'registrado_por', 'fecha_actualizacion'])

    if not atencion.detalles.exists():
        _copiar_servicios_cita(atencion)

    _cambiar_estado_cita(cita, 'EN_ATENCION', usuario, 'Atencion iniciada')
    return atencion


@transaction.atomic
def agregar_servicios_atencion(atencion_id, servicios_data, usuario):
    atencion = AtencionServicio.objects.select_for_update().select_related(
        'id_cita',
        'codigo_barbero',
        'codigo_cliente',
    ).get(pk=atencion_id)
    _validar_barbero_atencion(atencion.id_cita, usuario)

    if atencion.estado != 'EN_ATENCION':
        raise ValidationError('Solo se pueden agregar servicios mientras la atencion esta en curso.')

    ids = [item['id_servicio'] for item in servicios_data]
    servicios = Servicio.objects.filter(pk__in=ids, estado='ACTIVO')
    servicios_por_id = {servicio.pk: servicio for servicio in servicios}
    _validar_servicios_habilitados(atencion.codigo_barbero, servicios)

    for item in servicios_data:
        servicio = servicios_por_id[item['id_servicio']]
        cantidad = item.get('cantidad') or 1
        precio = servicio.precio
        subtotal = precio * Decimal(cantidad)
        detalle, creado = DetalleAtencionServicio.objects.get_or_create(
            id_atencion=atencion,
            id_servicio=servicio,
            defaults={
                'precio_unitario': precio,
                'cantidad': cantidad,
                'subtotal': subtotal,
                'observacion': (item.get('observacion') or '').strip(),
            },
        )
        if not creado:
            detalle.cantidad += cantidad
            detalle.subtotal = detalle.precio_unitario * Decimal(detalle.cantidad)
            observacion = (item.get('observacion') or '').strip()
            if observacion:
                detalle.observacion = observacion
            detalle.save(update_fields=['cantidad', 'subtotal', 'observacion'])

    atencion.recalcular_total()
    return atencion


@transaction.atomic
def finalizar_atencion(atencion_id, usuario, observaciones=''):
    atencion = AtencionServicio.objects.select_for_update().select_related(
        'id_cita',
        'codigo_barbero',
        'codigo_cliente',
    ).prefetch_related('detalles').get(pk=atencion_id)
    _validar_barbero_atencion(atencion.id_cita, usuario)

    if atencion.estado == 'FINALIZADA':
        raise ValidationError('La atencion ya fue finalizada.')
    if atencion.estado != 'EN_ATENCION':
        raise ValidationError('Solo se puede finalizar una atencion en curso.')
    if not atencion.detalles.exists():
        raise ValidationError('La atencion debe tener al menos un servicio realizado.')

    atencion.estado = 'FINALIZADA'
    atencion.hora_fin = timezone.now()
    atencion.observaciones = (observaciones or atencion.observaciones or '').strip()
    atencion.listo_para_cobro = True
    atencion.recalcular_total()
    atencion.save(update_fields=[
        'estado',
        'hora_fin',
        'observaciones',
        'listo_para_cobro',
        'fecha_actualizacion',
    ])

    _cambiar_estado_cita(atencion.id_cita, 'FINALIZADA', usuario, 'Atencion finalizada')
    return atencion


@transaction.atomic
def cambiar_estado_atencion(atencion_id, estado, usuario, observaciones=''):
    if estado not in ['CANCELADA', 'NO_ASISTIO']:
        raise ValidationError({'estado': 'Estado invalido para esta accion.'})

    atencion = AtencionServicio.objects.select_for_update().select_related('id_cita').get(pk=atencion_id)
    _validar_barbero_atencion(atencion.id_cita, usuario)
    if atencion.estado == 'FINALIZADA':
        raise ValidationError('No se puede cambiar una atencion finalizada.')

    atencion.estado = estado
    atencion.observaciones = (observaciones or atencion.observaciones or '').strip()
    atencion.hora_fin = timezone.now()
    atencion.listo_para_cobro = False
    atencion.save(update_fields=['estado', 'observaciones', 'hora_fin', 'listo_para_cobro', 'fecha_actualizacion'])
    _cambiar_estado_cita(atencion.id_cita, estado, usuario, f'Atencion marcada como {estado}')
    return atencion
