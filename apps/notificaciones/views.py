from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.seguridad.permissions import EsAdmin, EsCualquierUsuario
from apps.seguridad.views import registrar_bitacora

from .models import Notificacion, NotificacionUsuario, PushSubscription
from .serializers import (
    NotificacionCrearSerializer,
    NotificacionSerializer,
    NotificacionUsuarioSerializer,
    PushSubscriptionSerializer,
)
from .services import crear_notificacion, enviar_notificacion_push


@extend_schema(tags=['CU22 - Gestionar Notificaciones Push'])
class VapidPublicKeyView(APIView):
    permission_classes = [EsCualquierUsuario]

    def get(self, request):
        return Response({'vapid_public_key': getattr(settings, 'VAPID_PUBLIC_KEY', '')})


@extend_schema(tags=['CU22 - Gestionar Notificaciones Push'])
class PushSubscriptionView(APIView):
    permission_classes = [EsCualquierUsuario]
    serializer_class = PushSubscriptionSerializer

    @extend_schema(
        summary='Guardar suscripcion push',
        request=PushSubscriptionSerializer,
        responses={201: PushSubscriptionSerializer, 400: OpenApiResponse(description='Datos invalidos.')},
        examples=[
            OpenApiExample(
                'Suscripcion',
                value={
                    'endpoint': 'https://fcm.googleapis.com/fcm/send/...',
                    'keys': {'p256dh': 'clave-p256dh', 'auth': 'clave-auth'},
                    'navegador': 'Chrome',
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = PushSubscriptionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = getattr(request, 'usuario_actual', None)
        data = serializer.validated_data
        suscripcion, _ = PushSubscription.objects.update_or_create(
            endpoint=data['endpoint'],
            defaults={
                'usuario': usuario,
                'p256dh': data['p256dh'],
                'auth': data['auth'],
                'navegador': data.get('navegador') or request.META.get('HTTP_USER_AGENT', ''),
                'activa': True,
            },
        )
        registrar_bitacora(request, 'SUSCRIBIR_PUSH', f'Suscripcion push guardada: {suscripcion.id}.')
        return Response(
            {'mensaje': 'Suscripcion push guardada correctamente.', 'suscripcion': PushSubscriptionSerializer(suscripcion).data},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        endpoint = request.data.get('endpoint')
        if not endpoint:
            return Response({'endpoint': 'El endpoint es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
        PushSubscription.objects.filter(endpoint=endpoint).update(activa=False)
        registrar_bitacora(request, 'DESUSCRIBIR_PUSH', 'Suscripcion push desactivada.')
        return Response({'mensaje': 'Suscripcion push desactivada correctamente.'}, status=status.HTTP_200_OK)


@extend_schema(tags=['CU22 - Gestionar Notificaciones Push'])
class NotificacionListCreateView(APIView):
    permission_classes = [EsAdmin]
    serializer_class = NotificacionSerializer

    def get(self, request):
        notificaciones = Notificacion.objects.select_related('usuario_destino', 'usuario_destino__id_rol').all()
        tipo = request.query_params.get('tipo')
        estado = request.query_params.get('estado_envio')
        if tipo:
            notificaciones = notificaciones.filter(tipo=tipo.upper())
        if estado:
            notificaciones = notificaciones.filter(estado_envio=estado.upper())
        return Response(NotificacionSerializer(notificaciones, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Crear y enviar notificacion',
        request=NotificacionCrearSerializer,
        responses={201: NotificacionSerializer, 400: OpenApiResponse(description='Datos invalidos.')},
    )
    def post(self, request):
        serializer = NotificacionCrearSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        notificacion = crear_notificacion(
            tipo=data['tipo'],
            titulo=data['titulo'],
            mensaje=data['mensaje'],
            url=data.get('url', ''),
            usuario_destino=data.get('usuario_destino'),
            rol_destino=data.get('rol_destino', ''),
            enviar_push=data.get('enviar_push', True),
        )
        registrar_bitacora(request, 'CREAR_NOTIFICACION', f'Notificacion creada: {notificacion.id_notificacion}.')
        return Response(
            {'mensaje': 'Notificacion creada correctamente.', 'notificacion': NotificacionSerializer(notificacion).data},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['CU22 - Gestionar Notificaciones Push'])
class NotificacionReenviarView(APIView):
    permission_classes = [EsAdmin]

    def post(self, request, id_notificacion):
        notificacion = Notificacion.objects.filter(pk=id_notificacion).first()
        if not notificacion:
            return Response({'error': 'Notificacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        notificacion = enviar_notificacion_push(notificacion)
        return Response({'mensaje': 'Reenvio procesado.', 'notificacion': NotificacionSerializer(notificacion).data})


@extend_schema(tags=['CU22 - Gestionar Notificaciones Push'])
class MisNotificacionesView(APIView):
    permission_classes = [EsCualquierUsuario]

    def get(self, request):
        usuario = getattr(request, 'usuario_actual', None)
        notificaciones = NotificacionUsuario.objects.select_related(
            'notificacion',
            'notificacion__usuario_destino',
        ).filter(usuario=usuario)
        leida = request.query_params.get('leida')
        if leida is not None:
            notificaciones = notificaciones.filter(leida=str(leida).lower() == 'true')
        return Response(NotificacionUsuarioSerializer(notificaciones, many=True).data)


@extend_schema(tags=['CU22 - Gestionar Notificaciones Push'])
class MarcarNotificacionLeidaView(APIView):
    permission_classes = [EsCualquierUsuario]

    def post(self, request, id_notificacion_usuario):
        usuario = getattr(request, 'usuario_actual', None)
        notificacion_usuario = NotificacionUsuario.objects.filter(
            pk=id_notificacion_usuario,
            usuario=usuario,
        ).first()
        if not notificacion_usuario:
            return Response({'error': 'Notificacion no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        notificacion_usuario.leida = True
        notificacion_usuario.fecha_lectura = timezone.now()
        notificacion_usuario.save(update_fields=['leida', 'fecha_lectura'])
        return Response({'mensaje': 'Notificacion marcada como leida.'})
