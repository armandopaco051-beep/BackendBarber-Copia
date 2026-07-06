from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.citas.models import Cita
from apps.citas.serializers import CitaSerializer
from apps.servicios.models import Servicio

from .models import EncuestaSatisfaccion, OpcionRespuestaEncuesta, PreguntaEncuesta, ReclamoSugerencia


class ClienteCitaSerializer(CitaSerializer):
    # Serializer para reservar/reprogramar citas desde la vista cliente.
    # Inyecta codigo_cliente desde el token, no desde el frontend.
    def to_internal_value(self, data):
        data = data.copy()
        cliente = self.context.get('cliente')
        if cliente:
            data['codigo_cliente'] = cliente.codigo
        return super().to_internal_value(data)


class OpcionRespuestaEncuestaSerializer(serializers.ModelSerializer):
    # Opcion visible para una pregunta de tipo OPCION_UNICA o ESCALA.
    class Meta:
        model = OpcionRespuestaEncuesta
        fields = ['id_opcion', 'texto', 'valor', 'orden']

    def validate_texto(self, value):
        texto = value.strip()
        if not texto:
            raise serializers.ValidationError('La opcion de respuesta no puede estar vacia.')
        return texto


class PreguntaEncuestaSerializer(serializers.ModelSerializer):
    # Pregunta de la encuesta con sus opciones de respuesta.
    opciones = OpcionRespuestaEncuestaSerializer(many=True, required=False)
    tipo_respuesta = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = PreguntaEncuesta
        fields = ['id_pregunta', 'texto', 'tipo_respuesta', 'orden', 'obligatoria', 'opciones']

    def validate_texto(self, value):
        texto = value.strip()
        if not texto:
            raise serializers.ValidationError('La pregunta no puede estar vacia.')
        return texto

    def validate_tipo_respuesta(self, value):
        tipo = value.upper()
        if tipo not in dict(PreguntaEncuesta.TIPOS_RESPUESTA):
            raise serializers.ValidationError('Tipo de respuesta invalido.')
        return tipo

    def validate(self, data):
        # CU30: las preguntas de escala/opcion deben tener respuestas; las de texto son abiertas.
        tipo = data.get('tipo_respuesta', 'ESCALA')
        opciones = data.get('opciones', [])

        if tipo in ['OPCION_UNICA', 'ESCALA'] and not opciones:
            raise serializers.ValidationError({'opciones': 'La pregunta debe tener opciones de respuesta.'})
        if tipo == 'TEXTO' and opciones:
            raise serializers.ValidationError({'opciones': 'Las preguntas de texto no deben tener opciones.'})

        textos = [opcion.get('texto', '').strip().lower() for opcion in opciones]
        if len(textos) != len(set(textos)):
            raise serializers.ValidationError({'opciones': 'No puede repetir opciones dentro de la misma pregunta.'})

        return data


class EncuestaSatisfaccionSerializer(serializers.ModelSerializer):
    # Serializer del CU30: crea y administra encuestas completas con preguntas y opciones.
    preguntas = PreguntaEncuestaSerializer(many=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = EncuestaSatisfaccion
        fields = [
            'id_encuesta',
            'titulo',
            'descripcion',
            'estado',
            'preguntas',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def validate_titulo(self, value):
        # CU30: evita duplicar encuestas con el mismo titulo.
        titulo = value.strip()
        if not titulo:
            raise serializers.ValidationError('El titulo de la encuesta es obligatorio.')

        duplicada = EncuestaSatisfaccion.objects.filter(titulo__iexact=titulo)
        if self.instance:
            duplicada = duplicada.exclude(pk=self.instance.pk)
        if duplicada.exists():
            raise serializers.ValidationError('Ya existe una encuesta con ese titulo.')
        return titulo

    def validate_estado(self, value):
        # CU30: solo estados definidos en el modelo permiten publicar o retirar encuestas.
        estado = value.upper()
        if estado not in dict(EncuestaSatisfaccion.ESTADOS):
            raise serializers.ValidationError('Estado invalido.')
        return estado

    def validate_preguntas(self, value):
        # CU30: una encuesta sin preguntas no puede activarse para clientes atendidos.
        if not value:
            raise serializers.ValidationError('La encuesta debe tener al menos una pregunta.')
        textos = [pregunta.get('texto', '').strip().lower() for pregunta in value]
        if len(textos) != len(set(textos)):
            raise serializers.ValidationError('No puede repetir preguntas dentro de la encuesta.')
        return value

    def _guardar_preguntas(self, encuesta, preguntas):
        # Reemplaza la estructura completa para mantener sincronizadas preguntas y opciones.
        PreguntaEncuesta.objects.filter(id_encuesta=encuesta).delete()
        for indice_pregunta, pregunta_data in enumerate(preguntas, start=1):
            opciones = pregunta_data.pop('opciones', [])
            pregunta_data.setdefault('orden', indice_pregunta)
            pregunta = PreguntaEncuesta.objects.create(id_encuesta=encuesta, **pregunta_data)
            OpcionRespuestaEncuesta.objects.bulk_create([
                OpcionRespuestaEncuesta(
                    id_pregunta=pregunta,
                    texto=opcion['texto'],
                    valor=opcion.get('valor'),
                    orden=opcion.get('orden', indice_opcion),
                )
                for indice_opcion, opcion in enumerate(opciones, start=1)
            ])

    @transaction.atomic
    def create(self, validated_data):
        # CU30: guarda encuesta, preguntas y opciones en una sola transaccion.
        preguntas = validated_data.pop('preguntas', [])
        encuesta = EncuestaSatisfaccion.objects.create(**validated_data)
        self._guardar_preguntas(encuesta, preguntas)
        return encuesta

    @transaction.atomic
    def update(self, instance, validated_data):
        # CU30: conserva la encuesta y reconstruye sus preguntas si el administrador las modifica.
        preguntas = validated_data.pop('preguntas', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if preguntas is not None:
            self._guardar_preguntas(instance, preguntas)

        return instance

    @extend_schema_field(PreguntaEncuestaSerializer(many=True))
    def get_preguntas(self, obj):
        return PreguntaEncuestaSerializer(obj.preguntas.all(), many=True).data


class ReclamoSugerenciaSerializer(serializers.ModelSerializer):
    # Serializer del CU31: registra reclamos/sugerencias del cliente y seguimiento admin.
    id_cita = serializers.PrimaryKeyRelatedField(queryset=Cita.objects.all(), required=False, allow_null=True)
    id_servicio = serializers.PrimaryKeyRelatedField(queryset=Servicio.objects.all(), required=False, allow_null=True)
    codigo_cliente = serializers.PrimaryKeyRelatedField(read_only=True)
    cliente = serializers.SerializerMethodField(read_only=True)
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True, allow_null=True)
    tipo_solicitud = serializers.CharField(max_length=20)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = ReclamoSugerencia
        fields = [
            'id_solicitud',
            'codigo_cliente',
            'cliente',
            'tipo_solicitud',
            'detalle',
            'id_cita',
            'id_servicio',
            'servicio',
            'estado',
            'respuesta_admin',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['codigo_cliente', 'fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_cliente(self, obj):
        return f"{obj.codigo_cliente.nombre} {obj.codigo_cliente.apellido}".strip()

    def validate_tipo_solicitud(self, value):
        tipo = value.upper()
        if tipo not in dict(ReclamoSugerencia.TIPOS_SOLICITUD):
            raise serializers.ValidationError('Tipo de solicitud invalido.')
        return tipo

    def validate_detalle(self, value):
        detalle = value.strip()
        if not detalle:
            raise serializers.ValidationError('El detalle de la solicitud no puede estar vacio.')
        return detalle

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(ReclamoSugerencia.ESTADOS):
            raise serializers.ValidationError('Estado invalido.')
        return estado

    def validate(self, data):
        # CU31: valida que la solicitud pertenezca al cliente autenticado y a referencias reales.
        request = self.context.get('request')
        usuario = getattr(request, 'usuario_actual', None) if request else None
        instance = getattr(self, 'instance', None)

        cliente = getattr(instance, 'codigo_cliente', None) or usuario
        cita = data.get('id_cita', getattr(instance, 'id_cita', None))
        servicio = data.get('id_servicio', getattr(instance, 'id_servicio', None))
        tipo = data.get('tipo_solicitud', getattr(instance, 'tipo_solicitud', None))
        detalle = data.get('detalle', getattr(instance, 'detalle', None))

        if not cliente or not cliente.es_cliente:
            raise serializers.ValidationError({'codigo_cliente': 'Cliente no registrado.'})
        if cita and cita.codigo_cliente_id != cliente.codigo:
            raise serializers.ValidationError({'id_cita': 'La cita no pertenece al cliente autenticado.'})
        if servicio and servicio.estado != 'ACTIVO':
            raise serializers.ValidationError({'id_servicio': 'El servicio relacionado debe estar activo.'})

        # Evita registrar el mismo reclamo/sugerencia pendiente para la misma referencia.
        duplicado = ReclamoSugerencia.objects.filter(
            codigo_cliente=cliente,
            tipo_solicitud=tipo,
            detalle__iexact=detalle,
            estado__in=['PENDIENTE', 'EN_REVISION'],
        )
        if cita:
            duplicado = duplicado.filter(id_cita=cita)
        else:
            duplicado = duplicado.filter(id_cita__isnull=True)
        if servicio:
            duplicado = duplicado.filter(id_servicio=servicio)
        else:
            duplicado = duplicado.filter(id_servicio__isnull=True)
        if instance:
            duplicado = duplicado.exclude(pk=instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError('Ya existe una solicitud pendiente similar.')

        return data

    def create(self, validated_data):
        # CU31: toda solicitud nueva inicia pendiente para revision del administrador.
        request = self.context.get('request')
        cliente = getattr(request, 'usuario_actual', None) if request else None
        validated_data.pop('estado', None)
        return ReclamoSugerencia.objects.create(codigo_cliente=cliente, estado='PENDIENTE', **validated_data)


class RespuestaReclamoSugerenciaSerializer(serializers.Serializer):
    # Serializer del CU32: valida la respuesta administrativa y el nuevo estado.
    respuesta_admin = serializers.CharField()
    estado = serializers.CharField(max_length=20)

    ESTADOS_RESPUESTA = ['EN_REVISION', 'REVISADO', 'RESUELTO', 'CERRADO']

    def validate_respuesta_admin(self, value):
        respuesta = value.strip()
        if not respuesta:
            raise serializers.ValidationError('La respuesta no puede estar vacia.')
        return respuesta

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in self.ESTADOS_RESPUESTA:
            raise serializers.ValidationError('Estado invalido para responder la solicitud.')
        return estado

    def update(self, instance, validated_data):
        # Guarda la accion tomada y el estado final definido por el administrador.
        instance.respuesta_admin = validated_data['respuesta_admin']
        instance.estado = validated_data['estado']
        instance.save(update_fields=['respuesta_admin', 'estado', 'fecha_actualizacion'])
        return instance
