from datetime import datetime, timedelta

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.seguridad.models import AsistenciaBarbero, BloqueoHorario, HorarioLaboral, Usuario
from apps.servicios.models import Servicio

from .models import BarberoServicio, Cita, EstadoCita, HistorialEstadoCita


DIAS_SEMANA = {
    0: 'LUNES',
    1: 'MARTES',
    2: 'MIERCOLES',
    3: 'JUEVES',
    4: 'VIERNES',
    5: 'SABADO',
    6: 'DOMINGO',
}

ESTADOS_CITA = [
    'PENDIENTE',
    'CONFIRMADA',
    'EN_ATENCION',
    'FINALIZADA',
    'CANCELADA',
    'REPROGRAMADA',
    'NO_ASISTIO',
    'ANULADA',
]

ESTADOS_NO_BLOQUEAN_HORARIO = ['CANCELADA', 'REPROGRAMADA', 'ANULADA']


# Convierte textos del frontend a formato uniforme de estados.
# Ejemplo: "En atencion" -> "EN_ATENCION".
def normalizar_estado(value):
    return value.strip().upper().replace(' ', '_')


# Calcula hora_fin sumando la duracion del servicio a la hora_inicio.
def calcular_hora_fin(fecha, hora_inicio, duracion_minutos):
    inicio = datetime.combine(fecha, hora_inicio)
    fin = inicio + timedelta(minutes=duracion_minutos)
    return fin.time()


# Busca o crea el estado de cita en agenda.estado_cita.
def obtener_estado_cita(nombre):
    estado, _ = EstadoCita.objects.get_or_create(nombre=normalizar_estado(nombre))
    return estado


def obtener_valor_data(data, *nombres):
    # Lee un valor usando varios posibles nombres enviados desde el frontend.
    for nombre in nombres:
        if nombre in data and data.get(nombre) not in [None, '']:
            return data.get(nombre)
    return None


def normalizar_fecha_data(valor):
    # DRF entiende YYYY-MM-DD, pero el formulario puede enviar DD/MM/YYYY.
    if not valor or '-' in str(valor):
        return valor
    try:
        return datetime.strptime(str(valor), '%d/%m/%Y').date().isoformat()
    except ValueError:
        return valor


# Serializer de solo lectura para listar estados de cita.
class EstadoCitaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstadoCita
        fields = ['id_estado', 'nombre']


# Serializer de agenda.barbero_servicio.
# CRUD para habilitar que un barbero pueda realizar un servicio.
class BarberoServicioSerializer(serializers.ModelSerializer):
    codigo_barbero = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='barbero')
    )
    id_servicio = serializers.PrimaryKeyRelatedField(
        queryset=Servicio.objects.filter(estado='ACTIVO')
    )
    barbero = serializers.SerializerMethodField(read_only=True)
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = BarberoServicio
        fields = [
            'id_barbero_servicio',
            'codigo_barbero',
            'barbero',
            'id_servicio',
            'servicio',
            'estado',
            'fecha_registro',
        ]
        read_only_fields = ['fecha_registro']

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        # Campo de lectura para mostrar nombre completo del barbero.
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    def validate_estado(self, value):
        # Solo permite activar o inactivar la habilitacion.
        estado = value.upper()
        if estado not in ['ACTIVO', 'INACTIVO']:
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate(self, data):
        # Valida rol Barbero, servicio activo y que no exista duplicado.
        instance = getattr(self, 'instance', None)
        barbero = data.get('codigo_barbero', getattr(instance, 'codigo_barbero', None))
        servicio = data.get('id_servicio', getattr(instance, 'id_servicio', None))

        if not barbero or not barbero.es_barbero:
            raise serializers.ValidationError({"codigo_barbero": "El usuario seleccionado debe tener rol Barbero."})

        if servicio.estado != 'ACTIVO':
            raise serializers.ValidationError({"id_servicio": "El servicio debe estar activo."})

        duplicado = BarberoServicio.objects.filter(codigo_barbero=barbero, id_servicio=servicio)
        if instance:
            duplicado = duplicado.exclude(pk=instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError("Este barbero ya esta habilitado para ese servicio.")

        return data


# Serializer del historial de estados de una cita.
# Se usa para reportar los cambios: estado anterior, estado nuevo, usuario y fecha.
class HistorialEstadoCitaSerializer(serializers.ModelSerializer):
    estado_anterior_nombre = serializers.CharField(source='estado_anterior.nombre', read_only=True)
    estado_nuevo_nombre = serializers.CharField(source='estado_nuevo.nombre', read_only=True)
    cambiado_por_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = HistorialEstadoCita
        fields = [
            'id_historial',
            'id_cita',
            'estado_anterior',
            'estado_anterior_nombre',
            'estado_nuevo',
            'estado_nuevo_nombre',
            'observacion',
            'fecha_cambio',
            'cambiado_por',
            'cambiado_por_nombre',
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_cambiado_por_nombre(self, obj):
        if not obj.cambiado_por:
            return None
        return f"{obj.cambiado_por.nombre} {obj.cambiado_por.apellido}".strip()


# Serializer principal del CU11.
# Aqui vive la logica que evita citas invalidas o cruzadas.
class CitaSerializer(serializers.ModelSerializer):
    codigo_cliente = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='cliente')
    )
    codigo_barbero = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='barbero')
    )
    id_servicio = serializers.PrimaryKeyRelatedField(
        queryset=Servicio.objects.filter(estado='ACTIVO')
    )
    cliente = serializers.SerializerMethodField(read_only=True)
    barbero = serializers.SerializerMethodField(read_only=True)
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)
    estado = serializers.CharField(required=False, write_only=True)
    estado_nombre = serializers.CharField(source='id_estadoc.nombre', read_only=True)
    hora_fin = serializers.TimeField(read_only=True)
    precio_base = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    registrado_por = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Cita
        fields = [
            'id_cita',
            'codigo_cliente',
            'cliente',
            'codigo_barbero',
            'barbero',
            'id_servicio',
            'servicio',
            'fecha',
            'hora_inicio',
            'hora_fin',
            'estado',
            'estado_nombre',
            'observacion',
            'motivo_cancelacion',
            'precio_base',
            'registrado_por',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def to_internal_value(self, data):
        # Compatibilidad con el frontend de citas:
        # el backend espera codigo_cliente, codigo_barbero, id_servicio y hora_inicio,
        # pero el formulario puede enviar cliente, barbero, servicio u hora.
        data = data.copy()

        alias_campos = {
            'codigo_cliente': ['codigo_cliente', 'codigoCliente', 'cliente', 'id_cliente', 'idCliente'],
            'codigo_barbero': ['codigo_barbero', 'codigoBarbero', 'barbero', 'id_barbero', 'idBarbero'],
            'id_servicio': ['id_servicio', 'idServicio', 'servicio'],
            'hora_inicio': ['hora_inicio', 'horaInicio', 'hora', 'hora_cita', 'horaCita'],
            'motivo_cancelacion': ['motivo_cancelacion', 'motivoCancelacion'],
        }

        for campo_backend, nombres_frontend in alias_campos.items():
            if campo_backend not in data:
                valor = obtener_valor_data(data, *nombres_frontend)
                if valor is not None:
                    data[campo_backend] = valor

        if 'fecha' in data:
            data['fecha'] = normalizar_fecha_data(data.get('fecha'))
        elif 'date' in data:
            data['fecha'] = normalizar_fecha_data(data.get('date'))

        return super().to_internal_value(data)

    @extend_schema_field(serializers.CharField())
    def get_cliente(self, obj):
        return f"{obj.codigo_cliente.nombre} {obj.codigo_cliente.apellido}".strip()

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    def validate_estado(self, value):
        # Valida que el estado enviado exista dentro de los estados permitidos.
        estado = normalizar_estado(value)
        if estado not in ESTADOS_CITA:
            raise serializers.ValidationError("Estado de cita invalido.")
        return estado

    def validate(self, data):
        # Validacion general para crear o actualizar una cita.
        # Reune cliente, barbero, servicio, horario laboral, asistencia y bloqueos.
        instance = getattr(self, 'instance', None)
        cliente = data.get('codigo_cliente', getattr(instance, 'codigo_cliente', None))
        barbero = data.get('codigo_barbero', getattr(instance, 'codigo_barbero', None))
        servicio = data.get('id_servicio', getattr(instance, 'id_servicio', None))
        fecha = data.get('fecha', getattr(instance, 'fecha', None))
        hora_inicio = data.get('hora_inicio', getattr(instance, 'hora_inicio', None))
        estado = data.get('estado', getattr(getattr(instance, 'id_estadoc', None), 'nombre', 'CONFIRMADA'))

        if not cliente or not cliente.es_cliente:
            raise serializers.ValidationError({"codigo_cliente": "El usuario seleccionado debe tener rol Cliente."})
        if not barbero or not barbero.es_barbero:
            raise serializers.ValidationError({"codigo_barbero": "El usuario seleccionado debe tener rol Barbero."})
        if servicio.estado != 'ACTIVO':
            raise serializers.ValidationError({"id_servicio": "El servicio seleccionado debe estar activo."})

        hora_fin = calcular_hora_fin(fecha, hora_inicio, servicio.duracion_minutos)
        # hora_fin y precio_base se calculan en backend, no los envia el frontend.
        data['hora_fin'] = hora_fin
        data['precio_base'] = servicio.precio

        if estado in ESTADOS_NO_BLOQUEAN_HORARIO:
            return data

        self._validar_horario_laboral(barbero, fecha, hora_inicio, hora_fin)
        self._validar_asistencia(barbero, fecha)
        self._validar_bloqueos(barbero, fecha, hora_inicio, hora_fin)
        self._validar_cruce_citas(instance, barbero, fecha, hora_inicio, hora_fin)

        return data

    def _validar_horario_laboral(self, barbero, fecha, hora_inicio, hora_fin):
        # Verifica que la cita este dentro del horario laboral activo del barbero.
        dia_semana = DIAS_SEMANA[fecha.weekday()]
        horarios = HorarioLaboral.objects.filter(
            codigo_barbero=barbero,
            dia_semana__iexact=dia_semana,
            estado__iexact='ACTIVO',
            hora_inicio__lte=hora_inicio,
            hora_fin__gte=hora_fin,
        )
        if not horarios.exists():
            raise serializers.ValidationError("Barbero no disponible: no tiene horario laboral activo para ese dia y hora.")

        for horario in horarios:
            if horario.hora_inicio_descanso and horario.hora_fin_descanso:
                cruza_descanso = hora_inicio < horario.hora_fin_descanso and hora_fin > horario.hora_inicio_descanso
                if cruza_descanso:
                    raise serializers.ValidationError("El horario seleccionado cruza con el descanso del barbero.")

    def _validar_asistencia(self, barbero, fecha):
        # Si el barbero esta AUSENTE, PERMISO o INHABILITADO, no puede recibir citas.
        asistencia = AsistenciaBarbero.objects.filter(codigo_barbero=barbero, fecha=fecha).first()
        if asistencia and asistencia.estado in ['AUSENTE', 'PERMISO', 'INHABILITADO']:
            raise serializers.ValidationError("El barbero no esta disponible por asistencia registrada.")

    def _validar_bloqueos(self, barbero, fecha, hora_inicio, hora_fin):
        # Verifica que la cita no choque con bloqueos temporales.
        bloqueos = BloqueoHorario.objects.filter(
            codigo_barbero=barbero,
            fecha=fecha,
            estado='ACTIVO',
            hora_inicio__lt=hora_fin,
            hora_fin__gt=hora_inicio,
        )
        if bloqueos.exists():
            raise serializers.ValidationError("El horario seleccionado cruza con un bloqueo de horario.")

    def _validar_cruce_citas(self, instance, barbero, fecha, hora_inicio, hora_fin):
        # Evita que un barbero tenga dos citas en el mismo rango de horas.
        citas_cruzadas = Cita.objects.select_related('id_estadoc').filter(
            codigo_barbero=barbero,
            fecha=fecha,
            hora_inicio__lt=hora_fin,
            hora_fin__gt=hora_inicio,
        ).exclude(id_estadoc__nombre__in=ESTADOS_NO_BLOQUEAN_HORARIO)
        if instance:
            citas_cruzadas = citas_cruzadas.exclude(pk=instance.pk)
        if citas_cruzadas.exists():
            raise serializers.ValidationError("El barbero no esta disponible en ese horario.")

    @transaction.atomic
    def create(self, validated_data):
        # Crea la cita, asigna estado, registra usuario creador y crea historial inicial.
        estado_nombre = validated_data.pop('estado', 'CONFIRMADA')
        estado = obtener_estado_cita(estado_nombre)
        request = self.context.get('request')
        usuario_actual = getattr(request, 'usuario_actual', None) if request else None
        cita = Cita.objects.create(
            id_estadoc=estado,
            registrado_por=usuario_actual,
            **validated_data
        )
        HistorialEstadoCita.objects.create(
            id_cita=cita,
            estado_anterior=None,
            estado_nuevo=estado,
            observacion='Cita registrada',
            cambiado_por=usuario_actual,
        )
        return cita

    @transaction.atomic
    def update(self, instance, validated_data):
        # Actualiza la cita y, si cambia el estado, guarda el historial del cambio.
        estado_nombre = validated_data.pop('estado', None)
        estado_anterior = instance.id_estadoc

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if estado_nombre:
            instance.id_estadoc = obtener_estado_cita(estado_nombre)

        instance.save()

        estado_anterior_id = getattr(estado_anterior, 'id_estado', None)
        if estado_nombre and estado_anterior_id and estado_anterior_id != instance.id_estadoc_id:
            request = self.context.get('request')
            usuario_actual = getattr(request, 'usuario_actual', None) if request else None
            HistorialEstadoCita.objects.create(
                id_cita=instance,
                estado_anterior=estado_anterior,
                estado_nuevo=instance.id_estadoc,
                observacion=validated_data.get('motivo_cancelacion', ''),
                cambiado_por=usuario_actual,
            )

        return instance
