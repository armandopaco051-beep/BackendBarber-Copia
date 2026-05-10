from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import CategoriaServicio, Servicio


# Serializer del CRUD de categorias.
# Valida nombre unico y estado ACTIVO/INACTIVO.
class CategoriaServicioSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = CategoriaServicio
        fields = [
            'id_categoria',
            'nombre',
            'descripcion',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def validate_nombre(self, value):
        # No permite categorias vacias ni repetidas por nombre.
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre de la categoria no puede estar vacio.")

        queryset = CategoriaServicio.objects.filter(nombre__iexact=nombre)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Ya existe una categoria con este nombre.")
        return nombre

    def validate_estado(self, value):
        # Normaliza el estado enviado por frontend a mayusculas.
        estado = value.upper()
        estados_validos = dict(CategoriaServicio.ESTADOS)
        if estado not in estados_validos:
            raise serializers.ValidationError("Estado invalido.")
        return estado


# Serializer del CRUD de servicios.
# Valida categoria activa, precio, duracion y duplicados dentro de la categoria.
class ServicioSerializer(serializers.ModelSerializer):
    id_categoria = serializers.PrimaryKeyRelatedField(
        queryset=CategoriaServicio.objects.filter(estado='ACTIVO')
    )
    categoria = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = Servicio
        fields = [
            'id_servicio',
            'id_categoria',
            'categoria',
            'nombre',
            'descripcion',
            'precio',
            'duracion_minutos',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def to_internal_value(self, data):
        # Compatibilidad con frontend:
        # el modelo guarda duracion_minutos, pero algunos formularios envian
        # duracion, duration o duracionMinutos.
        data = data.copy()
        if 'duracion_minutos' not in data:
            for alias in ['duracion', 'duration', 'duracionMinutos']:
                if alias in data:
                    data['duracion_minutos'] = data[alias]
                    break
        return super().to_internal_value(data)

    @extend_schema_field(serializers.CharField())
    def get_categoria(self, obj):
        # Campo de lectura para mostrar el nombre de la categoria en el frontend.
        return obj.id_categoria.nombre

    def validate_nombre(self, value):
        # El nombre del servicio es obligatorio.
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del servicio no puede estar vacio.")
        return nombre

    def validate_precio(self, value):
        # Regla de negocio: el precio debe ser mayor a cero.
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0.")
        return value

    def validate_duracion_minutos(self, value):
        # Regla de negocio: la duracion debe ser mayor a cero.
        if value <= 0:
            raise serializers.ValidationError("La duracion debe ser mayor a 0 minutos.")
        return value

    def validate_estado(self, value):
        # Solo acepta ACTIVO o INACTIVO.
        estado = value.upper()
        estados_validos = dict(Servicio.ESTADOS)
        if estado not in estados_validos:
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate(self, data):
        # Evita duplicar un servicio con el mismo nombre dentro de la misma categoria.
        instance = getattr(self, 'instance', None)
        categoria = data.get('id_categoria', getattr(instance, 'id_categoria', None))
        nombre = data.get('nombre', getattr(instance, 'nombre', None))

        if categoria and categoria.estado != 'ACTIVO':
            raise serializers.ValidationError({"id_categoria": "La categoria seleccionada debe estar activa."})

        servicio_duplicado = Servicio.objects.filter(
            id_categoria=categoria,
            nombre__iexact=nombre,
        )
        if instance:
            servicio_duplicado = servicio_duplicado.exclude(pk=instance.pk)
        if servicio_duplicado.exists():
            raise serializers.ValidationError("Ya existe un servicio con ese nombre en esta categoria.")

        return data
