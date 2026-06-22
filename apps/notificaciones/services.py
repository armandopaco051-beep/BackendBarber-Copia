import json
import base64
import hashlib
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.seguridad.models import Usuario

from .models import Notificacion, NotificacionUsuario, PushSubscription


def obtener_vapid_private_key():
    private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
    if private_key and os.path.isfile(private_key):
        return private_key

    pem_base64 = getattr(settings, 'VAPID_PRIVATE_KEY_BASE64', '')
    pem_text = getattr(settings, 'VAPID_PRIVATE_KEY_PEM', '') or private_key

    if pem_base64:
        try:
            pem_bytes = base64.b64decode(pem_base64)
        except Exception:
            return ''
    elif pem_text and 'BEGIN EC PRIVATE KEY' in pem_text:
        pem_bytes = pem_text.replace('\\n', '\n').encode('utf-8')
    else:
        return private_key

    digest = hashlib.sha256(pem_bytes).hexdigest()[:16]
    key_path = Path(tempfile.gettempdir()) / f'vapid_{digest}.pem'
    if not key_path.exists():
        key_path.write_bytes(pem_bytes)
    return str(key_path)


def obtener_destinatarios(usuario_destino=None, rol_destino=''):
    if usuario_destino:
        return Usuario.objects.filter(pk=usuario_destino.pk)
    if rol_destino:
        return Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact=rol_destino)
    return Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='cliente')


def obtener_url_por_tipo(tipo):
    urls = {
        'PROMOCION': '/cliente/promociones',
        'NUEVO_BARBERO': '/cliente/dashboard',
        'CITA': '/cliente/citas',
        'RECORDATORIO_CITA': '/cliente/citas',
        'INVENTARIO': '/admin/productos',
        'SISTEMA': '/admin/notificaciones',
    }
    return urls.get((tipo or '').upper(), '/')


def enviar_push_suscripcion(suscripcion, notificacion):
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return False

    private_key = obtener_vapid_private_key()
    subject = getattr(settings, 'VAPID_SUBJECT', '')
    if not private_key or not subject:
        return False

    payload = json.dumps({
        'title': notificacion.titulo,
        'body': notificacion.mensaje,
        'url': notificacion.url or '/',
        'tipo': notificacion.tipo,
        'notificacion_id': notificacion.id_notificacion,
    })

    try:
        webpush(
            subscription_info={
                'endpoint': suscripcion.endpoint,
                'keys': {
                    'p256dh': suscripcion.p256dh,
                    'auth': suscripcion.auth,
                },
            },
            data=payload,
            vapid_private_key=private_key,
            vapid_claims={'sub': subject},
            ttl=3600,
        )
        return True
    except WebPushException as error:
        status_code = getattr(getattr(error, 'response', None), 'status_code', None)
        if status_code in [404, 410]:
            suscripcion.activa = False
            suscripcion.save(update_fields=['activa', 'fecha_actualizacion'])
        return False
    except Exception:
        return False


def enviar_notificacion_push(notificacion):
    enviados = 0
    fallidos = 0

    for destinatario in notificacion.destinatarios.select_related('usuario').all():
        subscripciones = PushSubscription.objects.filter(usuario=destinatario.usuario, activa=True)
        if not subscripciones.exists():
            destinatario.estado_envio = 'FALLIDA'
            destinatario.save(update_fields=['estado_envio'])
            fallidos += 1
            continue

        enviado_usuario = False
        for suscripcion in subscripciones:
            if enviar_push_suscripcion(suscripcion, notificacion):
                enviado_usuario = True
                enviados += 1
            else:
                fallidos += 1

        destinatario.estado_envio = 'ENVIADA' if enviado_usuario else 'FALLIDA'
        destinatario.save(update_fields=['estado_envio'])

    notificacion.enviados = enviados
    notificacion.fallidos = fallidos
    notificacion.enviada = enviados > 0
    if enviados and fallidos:
        notificacion.estado_envio = 'PARCIAL'
    elif enviados:
        notificacion.estado_envio = 'ENVIADA'
    else:
        notificacion.estado_envio = 'FALLIDA'
    notificacion.fecha_envio = timezone.now()
    notificacion.save(update_fields=[
        'enviados',
        'fallidos',
        'enviada',
        'estado_envio',
        'fecha_envio',
    ])
    return notificacion


def programar_envio_push(id_notificacion):
    def enviar_directo():
        notificacion = Notificacion.objects.filter(pk=id_notificacion).first()
        if notificacion:
            enviar_notificacion_push(notificacion)

    try:
        broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
        if not broker_url or not broker_url.startswith(('redis://', 'rediss://')):
            enviar_directo()
            return

        if broker_url.startswith(('redis://', 'rediss://')):
            import redis
            redis.Redis.from_url(broker_url, socket_connect_timeout=1).ping()

        from .tasks import enviar_notificacion_push_task
        enviar_notificacion_push_task.delay(id_notificacion)
    except Exception:
        enviar_directo()


@transaction.atomic
def crear_notificacion(tipo, titulo, mensaje, url='', usuario_destino=None, rol_destino='', enviar_push=True):
    notificacion = Notificacion.objects.create(
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        url=url or obtener_url_por_tipo(tipo),
        usuario_destino=usuario_destino,
        rol_destino=rol_destino or '',
    )

    destinatarios = obtener_destinatarios(usuario_destino, rol_destino)
    NotificacionUsuario.objects.bulk_create([
        NotificacionUsuario(notificacion=notificacion, usuario=usuario)
        for usuario in destinatarios
    ], ignore_conflicts=True)

    if enviar_push:
        transaction.on_commit(lambda: programar_envio_push(notificacion.id_notificacion))

    return notificacion


def notificar_promocion_activada(promocion):
    return crear_notificacion(
        tipo='PROMOCION',
        titulo='Nueva promocion disponible',
        mensaje=f'{promocion.nombre}: {promocion.descripcion or "Aprovecha esta promocion."}',
        url=f'/promociones/{promocion.id_promocion}',
        rol_destino='cliente',
        enviar_push=True,
    )


def notificar_nuevo_barbero(barbero):
    nombre = f'{barbero.nombre} {barbero.apellido}'.strip()
    especialidad = f' Especialidad: {barbero.especialidad}.' if barbero.especialidad else ''
    return crear_notificacion(
        tipo='NUEVO_BARBERO',
        titulo='Nuevo barbero disponible',
        mensaje=f'{nombre} ya forma parte de Blessed Barber Club.{especialidad}',
        url=f'/barberos/{barbero.codigo}',
        rol_destino='cliente',
        enviar_push=True,
    )


def notificar_recordatorio_cita(cita, usuario_destino):
    return crear_notificacion(
        tipo='RECORDATORIO_CITA',
        titulo='Recordatorio de cita',
        mensaje=f'Tienes una cita el {cita.fecha} a las {cita.hora_inicio}.',
        url=f'/mis-citas/{cita.id_cita}',
        usuario_destino=usuario_destino,
        enviar_push=True,
    )
