from rest_framework import serializers

from apps.seguridad.models import Usuario

from .models import Notificacion, NotificacionUsuario, PushSubscription


class PushSubscriptionSerializer(serializers.ModelSerializer):
    keys = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = PushSubscription
        fields = [
            'id',
            'usuario',
            'endpoint',
            'p256dh',
            'auth',
            'keys',
            'navegador',
            'activa',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['id', 'usuario', 'activa', 'fecha_registro', 'fecha_actualizacion']
        extra_kwargs = {
            'p256dh': {'required': False},
            'auth': {'required': False},
        }

    def validate(self, data):
        keys = data.pop('keys', {}) or {}
        data['p256dh'] = data.get('p256dh') or keys.get('p256dh')
        data['auth'] = data.get('auth') or keys.get('auth')

        if not data.get('endpoint'):
            raise serializers.ValidationError({'endpoint': 'El endpoint es obligatorio.'})
        if not data.get('p256dh'):
            raise serializers.ValidationError({'p256dh': 'La clave p256dh es obligatoria.'})
        if not data.get('auth'):
            raise serializers.ValidationError({'auth': 'La clave auth es obligatoria.'})
        return data


class NotificacionSerializer(serializers.ModelSerializer):
    usuario_destino_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Notificacion
        fields = [
            'id_notificacion',
            'tipo',
            'titulo',
            'mensaje',
            'url',
            'usuario_destino',
            'usuario_destino_nombre',
            'rol_destino',
            'enviada',
            'estado_envio',
            'enviados',
            'fallidos',
            'fecha_envio',
            'fecha_registro',
        ]
        read_only_fields = [
            'enviada',
            'estado_envio',
            'enviados',
            'fallidos',
            'fecha_envio',
            'fecha_registro',
        ]

    def get_usuario_destino_nombre(self, obj):
        if not obj.usuario_destino:
            return None
        return f"{obj.usuario_destino.nombre} {obj.usuario_destino.apellido}".strip()

    def validate_tipo(self, value):
        tipo = value.upper()
        if tipo not in dict(Notificacion.TIPOS):
            raise serializers.ValidationError('Tipo de notificacion invalido.')
        return tipo

    def validate_rol_destino(self, value):
        return (value or '').strip()


class NotificacionCrearSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=[tipo for tipo, _ in Notificacion.TIPOS])
    titulo = serializers.CharField(max_length=150)
    mensaje = serializers.CharField()
    url = serializers.CharField(required=False, allow_blank=True)
    usuario_destino = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').all(),
        required=False,
        allow_null=True
    )
    rol_destino = serializers.CharField(required=False, allow_blank=True)
    enviar_push = serializers.BooleanField(default=True)

    def validate(self, data):
        if data.get('usuario_destino') and data.get('rol_destino'):
            raise serializers.ValidationError('Debe enviar usuario_destino o rol_destino, no ambos.')
        return data


class NotificacionUsuarioSerializer(serializers.ModelSerializer):
    notificacion = NotificacionSerializer(read_only=True)

    class Meta:
        model = NotificacionUsuario
        fields = [
            'id_notificacion_usuario',
            'notificacion',
            'leida',
            'estado_envio',
            'fecha_lectura',
            'fecha_registro',
        ]
