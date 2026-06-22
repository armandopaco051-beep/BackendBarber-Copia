from django.urls import path

from .views import (
    MarcarNotificacionLeidaView,
    MisNotificacionesView,
    NotificacionListCreateView,
    NotificacionReenviarView,
    PushSubscriptionView,
    VapidPublicKeyView,
)


urlpatterns = [
    path('vapid-public-key/', VapidPublicKeyView.as_view(), name='notificaciones-vapid-public-key'),
    path('suscripciones/', PushSubscriptionView.as_view(), name='notificaciones-suscripciones'),
    path('notificaciones/', NotificacionListCreateView.as_view(), name='notificaciones-list-create'),
    path('notificaciones/<int:id_notificacion>/reenviar/', NotificacionReenviarView.as_view(), name='notificaciones-reenviar'),
    path('mis-notificaciones/', MisNotificacionesView.as_view(), name='mis-notificaciones'),
    path('mis-notificaciones/<int:id_notificacion_usuario>/leer/', MarcarNotificacionLeidaView.as_view(), name='mis-notificaciones-leer'),
]
