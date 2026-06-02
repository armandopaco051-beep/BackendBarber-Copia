from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.seguridad.models import Usuario

from .models import MetodoPago, PlanComision


# Serializers del paquete Ventas y Caja.
# En este ciclo solo se implementan:
# - CU13 MetodoPago
# - CU14 PlanComision


class MetodoPagoSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = MetodoPago
        fields = [
            'id_metodo_pago',
            'nombre',
            'descripcion',
            'requiere_referencia',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del metodo de pago es obligatorio.")

        duplicado = MetodoPago.objects.filter(nombre__iexact=nombre)
        if self.instance:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError("Ya existe un metodo de pago con ese nombre.")
        return nombre

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(MetodoPago.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado


class PlanComisionSerializer(serializers.ModelSerializer):
    codigo_barbero = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='barbero')
    )
    barbero_nombre = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = PlanComision
        fields = [
            'id_plan_comision',
            'nombre',
            'descripcion',
            'codigo_barbero',
            'barbero_nombre',
            'porcentaje_barbero',
            'porcentaje_barberia',
            'fecha_inicio',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_barbero_nombre(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del plan de comision es obligatorio.")
        return nombre

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(PlanComision.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_porcentaje_barbero(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("El porcentaje del barbero debe estar entre 0 y 100.")
        return value

    def validate_porcentaje_barberia(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("El porcentaje de la barberia debe estar entre 0 y 100.")
        return value

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        barbero = data.get('codigo_barbero', getattr(instance, 'codigo_barbero', None))
        porcentaje_barbero = data.get('porcentaje_barbero', getattr(instance, 'porcentaje_barbero', None))
        porcentaje_barberia = data.get('porcentaje_barberia', getattr(instance, 'porcentaje_barberia', None))
        estado = data.get('estado', getattr(instance, 'estado', 'ACTIVO'))
        fecha_inicio = data.get('fecha_inicio', getattr(instance, 'fecha_inicio', None))

        if not barbero:
            raise serializers.ValidationError({'codigo_barbero': 'El barbero es obligatorio.'})
        if not barbero.es_barbero:
            raise serializers.ValidationError({'codigo_barbero': 'El usuario seleccionado debe tener rol Barbero.'})
        if not fecha_inicio:
            raise serializers.ValidationError({'fecha_inicio': 'La fecha de inicio es obligatoria.'})
        if porcentaje_barbero is None:
            raise serializers.ValidationError({'porcentaje_barbero': 'El porcentaje del barbero es obligatorio.'})
        if porcentaje_barberia is None:
            raise serializers.ValidationError({'porcentaje_barberia': 'El porcentaje de la barberia es obligatorio.'})
        if (porcentaje_barbero + porcentaje_barberia) > 100:
            raise serializers.ValidationError('La suma de porcentaje_barbero y porcentaje_barberia no puede superar 100.')

        if estado == 'ACTIVO':
            planes_activos = PlanComision.objects.filter(
                codigo_barbero=barbero,
                estado='ACTIVO',
            )
            if instance:
                planes_activos = planes_activos.exclude(pk=instance.pk)
            if planes_activos.exists():
                raise serializers.ValidationError({
                    'codigo_barbero': 'Ya existe un plan de comision activo para ese barbero.'
                })

        return data
