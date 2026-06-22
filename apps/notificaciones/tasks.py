try:
    from celery import shared_task
except ImportError:
    def shared_task(func=None, **_kwargs):
        def decorator(inner):
            inner.delay = inner
            return inner
        return decorator(func) if func else decorator

from .models import Notificacion
from .services import enviar_notificacion_push


@shared_task
def enviar_notificacion_push_task(id_notificacion):
    notificacion = Notificacion.objects.filter(pk=id_notificacion).first()
    if not notificacion:
        return {'error': 'Notificacion no encontrada.'}

    notificacion = enviar_notificacion_push(notificacion)
    return {
        'id_notificacion': notificacion.id_notificacion,
        'estado_envio': notificacion.estado_envio,
        'enviados': notificacion.enviados,
        'fallidos': notificacion.fallidos,
    }
