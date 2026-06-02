from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import CategoriaProducto, Insumo, Marca, MovimientoInventario, Producto


class CategoriaProductoSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = CategoriaProducto
        fields = ['id_categoria', 'nombre', 'estado', 'fecha_registro', 'fecha_actualizacion']
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre de la categoria es obligatorio.")
        duplicado = CategoriaProducto.objects.filter(nombre__iexact=nombre)
        if self.instance:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError("Ya existe una categoria con ese nombre.")
        return nombre

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(CategoriaProducto.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado


class MarcaSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = Marca
        fields = ['id_marca', 'nombre', 'estado', 'fecha_registro', 'fecha_actualizacion']
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre de la marca es obligatorio.")
        duplicado = Marca.objects.filter(nombre__iexact=nombre)
        if self.instance:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError("Ya existe una marca con ese nombre.")
        return nombre

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(Marca.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado


class ProductoSerializer(serializers.ModelSerializer):
    id_categoria = serializers.PrimaryKeyRelatedField(queryset=CategoriaProducto.objects.filter(estado='ACTIVO'))
    id_marca = serializers.PrimaryKeyRelatedField(queryset=Marca.objects.filter(estado='ACTIVO'), required=False, allow_null=True)
    categoria_nombre = serializers.CharField(source='id_categoria.nombre', read_only=True)
    marca_nombre = serializers.CharField(source='id_marca.nombre', read_only=True, allow_null=True)
    stock_bajo = serializers.BooleanField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)
    tipo_producto = serializers.CharField(max_length=20)

    class Meta:
        model = Producto
        fields = [
            'id_producto',
            'id_categoria',
            'categoria_nombre',
            'id_marca',
            'marca_nombre',
            'nombre',
            'descripcion',
            'precio_venta',
            'cantidad_disponible',
            'stock_minimo',
            'tipo_producto',
            'estado',
            'stock_bajo',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion', 'stock_bajo']

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del producto es obligatorio.")
        return nombre

    def validate_tipo_producto(self, value):
        tipo = value.upper()
        if tipo not in dict(Producto.TIPOS_PRODUCTO):
            raise serializers.ValidationError("Tipo de producto invalido.")
        return tipo

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(Producto.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_cantidad_disponible(self, value):
        if value < 0:
            raise serializers.ValidationError("La cantidad disponible no puede ser negativa.")
        return value

    def validate_stock_minimo(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock minimo no puede ser negativo.")
        return value

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        categoria = data.get('id_categoria', getattr(instance, 'id_categoria', None))
        marca = data.get('id_marca', getattr(instance, 'id_marca', None))
        nombre = data.get('nombre', getattr(instance, 'nombre', None))
        precio_venta = data.get('precio_venta', getattr(instance, 'precio_venta', None))
        tipo_producto = data.get('tipo_producto', getattr(instance, 'tipo_producto', None))

        if categoria and categoria.estado != 'ACTIVO':
            raise serializers.ValidationError({'id_categoria': 'La categoria seleccionada debe estar activa.'})
        if marca and marca.estado != 'ACTIVO':
            raise serializers.ValidationError({'id_marca': 'La marca seleccionada debe estar activa.'})
        if tipo_producto in ['VENTA', 'AMBOS'] and (precio_venta is None or precio_venta <= 0):
            raise serializers.ValidationError({'precio_venta': 'El precio de venta debe ser mayor a 0 para productos de venta o ambos.'})

        duplicado = Producto.objects.filter(
            id_categoria=categoria,
            nombre__iexact=nombre,
        )
        if marca:
            duplicado = duplicado.filter(id_marca=marca)
        else:
            duplicado = duplicado.filter(id_marca__isnull=True)
        if instance:
            duplicado = duplicado.exclude(pk=instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError('Ya existe un producto con ese nombre para la misma categoria y marca.')

        return data


class InsumoSerializer(serializers.ModelSerializer):
    id_categoria = serializers.PrimaryKeyRelatedField(queryset=CategoriaProducto.objects.filter(estado='ACTIVO'))
    categoria_nombre = serializers.CharField(source='id_categoria.nombre', read_only=True)
    stock_bajo = serializers.BooleanField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = Insumo
        fields = [
            'id_insumo',
            'id_categoria',
            'categoria_nombre',
            'nombre',
            'descripcion',
            'unidad_medida',
            'cantidad_disponible',
            'stock_minimo',
            'estado',
            'stock_bajo',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion', 'stock_bajo']

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del insumo es obligatorio.")
        return nombre

    def validate_unidad_medida(self, value):
        unidad = value.strip()
        if not unidad:
            raise serializers.ValidationError("La unidad de medida es obligatoria.")
        return unidad

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(Insumo.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_cantidad_disponible(self, value):
        if value < 0:
            raise serializers.ValidationError("La cantidad disponible no puede ser negativa.")
        return value

    def validate_stock_minimo(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock minimo no puede ser negativo.")
        return value

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        categoria = data.get('id_categoria', getattr(instance, 'id_categoria', None))
        nombre = data.get('nombre', getattr(instance, 'nombre', None))

        if categoria and categoria.estado != 'ACTIVO':
            raise serializers.ValidationError({'id_categoria': 'La categoria seleccionada debe estar activa.'})

        duplicado = Insumo.objects.filter(
            id_categoria=categoria,
            nombre__iexact=nombre,
        )
        if instance:
            duplicado = duplicado.exclude(pk=instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError('Ya existe un insumo con ese nombre en la misma categoria.')

        return data


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='id_producto.nombre', read_only=True, allow_null=True)
    insumo_nombre = serializers.CharField(source='id_insumo.nombre', read_only=True, allow_null=True)
    usuario_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MovimientoInventario
        fields = [
            'id_movimiento',
            'id_producto',
            'producto_nombre',
            'id_insumo',
            'insumo_nombre',
            'tipo_movimiento',
            'cantidad',
            'motivo',
            'fecha',
            'usuario',
            'usuario_nombre',
        ]
        read_only_fields = ['fecha']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return f"{obj.usuario.nombre} {obj.usuario.apellido}".strip()
