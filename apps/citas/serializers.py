from datetime import datetime, timedelta

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.seguridad.models import AsistenciaBarbero, BloqueoHorario, HorarioLaboral, Usuario
from apps.servicios.models import Servicio

from .models import (
    BarberoServicio,
    AtencionServicio,
    Cita,
    DetalleAtencionServicio,
    DetalleServicioCita,
    DetallePromocion,
    EstadoCita,
    HistorialEstadoCita,
    Promocion,
)


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

ESTADOS_NO_BLOQUEAN_HORARIO = ['CANCELADA', 'ANULADA', 'NO_ASISTIO']


# Convierte textos del frontend a formato uniforme de estados.
# Ejemplo: "En atencion" -> "EN_ATENCION".
def normalizar_estado(value):
    return value.strip().upper().replace(' ', '_')


# Calcula hora_fin sumando la duracion del servicio a la hora_inicio.
def calcular_hora_fin(fecha, hora_inicio, duracion_minutos):
    inicio = datetime.combine(fecha, hora_inicio)
    fin = inicio + timedelta(minutes=duracion_minutos)
    return fin.time()


def calcular_total_servicios(servicios):
    return sum((servicio.precio for servicio in servicios), start=0)


def calcular_duracion_servicios(servicios):
    return sum((servicio.duracion_minutos for servicio in servicios), start=0)


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
        queryset=Servicio.objects.filter(estado='ACTIVO'),
        required=False,
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


class DetallePromocionSerializer(serializers.ModelSerializer):
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)
    estado_servicio = serializers.CharField(source='id_servicio.estado', read_only=True)

    class Meta:
        model = DetallePromocion
        fields = ['id_detalle', 'id_promocion', 'id_servicio', 'servicio', 'estado_servicio']


class PromocionSerializer(serializers.ModelSerializer):
    servicios = serializers.PrimaryKeyRelatedField(
        queryset=Servicio.objects.filter(estado='ACTIVO'),
        many=True,
    )
    servicios_detalle = serializers.SerializerMethodField(read_only=True)
    vigente_hoy = serializers.BooleanField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)
    tipo_descuento = serializers.CharField(max_length=20)

    class Meta:
        model = Promocion
        fields = [
            'id_promocion',
            'nombre',
            'descripcion',
            'tipo_descuento',
            'valor_descuento',
            'fecha_inicio',
            'fecha_fin',
            'estado',
            'servicios',
            'servicios_detalle',
            'vigente_hoy',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion', 'vigente_hoy']

    @extend_schema_field(DetallePromocionSerializer(many=True))
    def get_servicios_detalle(self, obj):
        detalles = obj.detalles_servicios.select_related('id_servicio').all()
        return DetallePromocionSerializer(detalles, many=True).data

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre de la promocion es obligatorio.")

        duplicada = Promocion.objects.filter(nombre__iexact=nombre)
        if self.instance:
            duplicada = duplicada.exclude(pk=self.instance.pk)
        if duplicada.exists():
            raise serializers.ValidationError("Ya existe una promocion con ese nombre.")
        return nombre

    def validate_tipo_descuento(self, value):
        tipo = value.upper()
        if tipo not in dict(Promocion.TIPOS_DESCUENTO):
            raise serializers.ValidationError("Tipo de descuento invalido.")
        return tipo

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(Promocion.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_valor_descuento(self, value):
        if value <= 0:
            raise serializers.ValidationError("El valor del descuento debe ser mayor a 0.")
        return value

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        fecha_inicio = data.get('fecha_inicio', getattr(instance, 'fecha_inicio', None))
        fecha_fin = data.get('fecha_fin', getattr(instance, 'fecha_fin', None))
        tipo_descuento = data.get('tipo_descuento', getattr(instance, 'tipo_descuento', None))
        valor_descuento = data.get('valor_descuento', getattr(instance, 'valor_descuento', None))
        servicios = data.get('servicios')

        if not fecha_inicio:
            raise serializers.ValidationError({'fecha_inicio': 'La fecha de inicio es obligatoria.'})
        if not fecha_fin:
            raise serializers.ValidationError({'fecha_fin': 'La fecha de fin es obligatoria.'})
        if fecha_inicio > fecha_fin:
            raise serializers.ValidationError({'fecha_fin': 'La fecha de fin debe ser mayor o igual a la fecha de inicio.'})
        if tipo_descuento == 'PORCENTAJE' and valor_descuento and valor_descuento > 100:
            raise serializers.ValidationError({'valor_descuento': 'El porcentaje no puede ser mayor a 100.'})

        if instance:
            if servicios is not None and not servicios:
                raise serializers.ValidationError({'servicios': 'Debe asociar al menos un servicio activo.'})
        elif not servicios:
            raise serializers.ValidationError({'servicios': 'Debe asociar al menos un servicio activo.'})

        return data

    def _actualizar_servicios(self, promocion, servicios):
        DetallePromocion.objects.filter(id_promocion=promocion).delete()
        DetallePromocion.objects.bulk_create([
            DetallePromocion(id_promocion=promocion, id_servicio=servicio)
            for servicio in servicios
        ])

    @transaction.atomic
    def create(self, validated_data):
        servicios = validated_data.pop('servicios', [])
        promocion = Promocion.objects.create(**validated_data)
        self._actualizar_servicios(promocion, servicios)
        return promocion

    @transaction.atomic
    def update(self, instance, validated_data):
        servicios = validated_data.pop('servicios', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if servicios is not None:
            self._actualizar_servicios(instance, servicios)

        return instance


class DetalleServicioCitaSerializer(serializers.ModelSerializer):
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)

    class Meta:
        model = DetalleServicioCita
        fields = [
            'id_detalle_cita',
            'id_servicio',
            'servicio',
            'precio_unitario',
            'duracion_minutos',
            'subtotal',
        ]


class ServicioCitaInputSerializer(serializers.Serializer):
    id_servicio = serializers.IntegerField()


class DetalleAtencionServicioSerializer(serializers.ModelSerializer):
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)

    class Meta:
        model = DetalleAtencionServicio
        fields = [
            'id_detalle_atencion',
            'id_servicio',
            'servicio',
            'precio_unitario',
            'cantidad',
            'subtotal',
            'observacion',
        ]


class ServicioAtencionInputSerializer(serializers.Serializer):
    id_servicio = serializers.IntegerField()
    cantidad = serializers.IntegerField(required=False, min_value=1, default=1)
    observacion = serializers.CharField(required=False, allow_blank=True)


class AtencionServicioSerializer(serializers.ModelSerializer):
    cliente = serializers.SerializerMethodField()
    barbero = serializers.SerializerMethodField()
    estado_cita = serializers.CharField(source='id_cita.id_estadoc.nombre', read_only=True)
    detalles = DetalleAtencionServicioSerializer(many=True, read_only=True)

    class Meta:
        model = AtencionServicio
        fields = [
            'id_atencion',
            'id_cita',
            'codigo_cliente',
            'cliente',
            'codigo_barbero',
            'barbero',
            'fecha',
            'hora_inicio',
            'hora_fin',
            'estado',
            'estado_cita',
            'observaciones',
            'total_servicios',
            'listo_para_cobro',
            'detalles',
            'registrado_por',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_cliente(self, obj):
        return f"{obj.codigo_cliente.nombre} {obj.codigo_cliente.apellido}".strip()

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()


class AtencionIniciarSerializer(serializers.Serializer):
    id_cita = serializers.IntegerField()


class AtencionAgregarServiciosSerializer(serializers.Serializer):
    servicios = ServicioAtencionInputSerializer(many=True)

    def validate_servicios(self, value):
        if not value:
            raise serializers.ValidationError('Debe enviar al menos un servicio.')
        ids = [item['id_servicio'] for item in value]
        servicios = Servicio.objects.filter(pk__in=ids, estado='ACTIVO')
        existentes = set(servicios.values_list('id_servicio', flat=True))
        faltantes = [id_servicio for id_servicio in ids if id_servicio not in existentes]
        if faltantes:
            raise serializers.ValidationError(f'Servicios activos no encontrados: {faltantes}.')
        return value


class AtencionFinalizarSerializer(serializers.Serializer):
    observaciones = serializers.CharField(required=False, allow_blank=True)


class AtencionCambiarEstadoSerializer(serializers.Serializer):
    observaciones = serializers.CharField(required=False, allow_blank=True)


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
    servicios = ServicioCitaInputSerializer(many=True, write_only=True, required=False)
    servicios_detalle = DetalleServicioCitaSerializer(many=True, read_only=True)
    estado = serializers.CharField(required=False, write_only=True)
    estado_nombre = serializers.CharField(source='id_estadoc.nombre', read_only=True)
    hora_fin = serializers.TimeField(read_only=True)
    precio_base = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal_servicios = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_estimado = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
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
            'servicios',
            'servicios_detalle',
            'fecha',
            'hora_inicio',
            'hora_fin',
            'estado',
            'estado_nombre',
            'observacion',
            'motivo_cancelacion',
            'precio_base',
            'subtotal_servicios',
            'total_estimado',
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
            'servicios': ['servicios'],
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

    def _obtener_servicios_validados(self, data, instance=None):
        servicios_data = data.pop('servicios', None)
        servicio_principal = data.get('id_servicio', getattr(instance, 'id_servicio', None))

        if servicios_data is None:
            if instance and 'id_servicio' not in data:
                servicios = [
                    detalle.id_servicio
                    for detalle in instance.servicios_detalle.select_related('id_servicio').all()
                ]
                if not servicios and servicio_principal:
                    servicios = [servicio_principal]
            else:
                servicios = [servicio_principal] if servicio_principal else []
        else:
            ids_servicios = []
            for item in servicios_data:
                id_servicio = item.get('id_servicio') if isinstance(item, dict) else item
                if id_servicio not in ids_servicios:
                    ids_servicios.append(id_servicio)
            servicios = list(Servicio.objects.filter(pk__in=ids_servicios, estado='ACTIVO'))
            servicios_por_id = {servicio.pk: servicio for servicio in servicios}
            faltantes = [id_servicio for id_servicio in ids_servicios if id_servicio not in servicios_por_id]
            if faltantes:
                raise serializers.ValidationError({'servicios': f'Servicios activos no encontrados: {faltantes}.'})
            servicios = [servicios_por_id[id_servicio] for id_servicio in ids_servicios]

        if not servicios:
            raise serializers.ValidationError({'servicios': 'Debe seleccionar al menos un servicio.'})

        data['id_servicio'] = servicios[0]
        data['_servicios_cita'] = servicios
        return servicios

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
        servicios = self._obtener_servicios_validados(data, instance)
        servicio = servicios[0]
        fecha = data.get('fecha', getattr(instance, 'fecha', None))
        hora_inicio = data.get('hora_inicio', getattr(instance, 'hora_inicio', None))
        estado = data.get('estado', getattr(getattr(instance, 'id_estadoc', None), 'nombre', 'CONFIRMADA'))

        if not cliente or not cliente.es_cliente:
            raise serializers.ValidationError({"codigo_cliente": "El usuario seleccionado debe tener rol Cliente."})
        if not barbero or not barbero.es_barbero:
            raise serializers.ValidationError({"codigo_barbero": "El usuario seleccionado debe tener rol Barbero."})
        asignaciones_barbero = BarberoServicio.objects.filter(codigo_barbero=barbero)
        if asignaciones_barbero.exists():
            servicios_no_habilitados = [
                servicio_item.nombre
                for servicio_item in servicios
                if not asignaciones_barbero.filter(id_servicio=servicio_item, estado='ACTIVO').exists()
            ]
            if servicios_no_habilitados:
                raise serializers.ValidationError({
                    "servicios": f"El barbero no esta habilitado para: {', '.join(servicios_no_habilitados)}."
                })

        duracion_total = calcular_duracion_servicios(servicios)
        subtotal_servicios = calcular_total_servicios(servicios)
        hora_fin = calcular_hora_fin(fecha, hora_inicio, duracion_total)
        # hora_fin y precio_base se calculan en backend, no los envia el frontend.
        data['hora_fin'] = hora_fin
        data['precio_base'] = servicio.precio
        data['subtotal_servicios'] = subtotal_servicios
        data['total_estimado'] = subtotal_servicios

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
        estado_asistencia = str(getattr(asistencia, 'estado', '')).upper()
        if asistencia and estado_asistencia in ['AUSENTE', 'PERMISO', 'INHABILITADO']:
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
        servicios = validated_data.pop('_servicios_cita')
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
        self._actualizar_servicios_cita(cita, servicios)
        return cita

    @transaction.atomic
    def update(self, instance, validated_data):
        # Actualiza la cita y, si cambia el estado, guarda el historial del cambio.
        servicios = validated_data.pop('_servicios_cita', None)
        estado_nombre = validated_data.pop('estado', None)
        estado_anterior = instance.id_estadoc

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if estado_nombre:
            instance.id_estadoc = obtener_estado_cita(estado_nombre)

        instance.save()

        if servicios is not None:
            self._actualizar_servicios_cita(instance, servicios)

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

    def _actualizar_servicios_cita(self, cita, servicios):
        DetalleServicioCita.objects.filter(id_cita=cita).delete()
        DetalleServicioCita.objects.bulk_create([
            DetalleServicioCita(
                id_cita=cita,
                id_servicio=servicio,
                precio_unitario=servicio.precio,
                duracion_minutos=servicio.duracion_minutos,
                subtotal=servicio.precio,
            )
            for servicio in servicios
        ])
