from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from apps.citas.models import AtencionServicio, Cita
from apps.inventario.models import Producto
from apps.seguridad.models import Usuario

from .models import (
    CategoriaServicio,
    DetallePaqueteServicio,
    DetalleProductoRecomendacion,
    DiagnosticoCapilar,
    PaqueteServicio,
    RecomendacionCuidado,
    Servicio,
    TrabajoPortafolio,
)


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


class DetallePaqueteServicioSerializer(serializers.ModelSerializer):
    # Representa un servicio incluido dentro de un paquete para respuestas de lectura.
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)
    precio = serializers.DecimalField(source='id_servicio.precio', max_digits=10, decimal_places=2, read_only=True)
    duracion_minutos = serializers.IntegerField(source='id_servicio.duracion_minutos', read_only=True)
    estado_servicio = serializers.CharField(source='id_servicio.estado', read_only=True)

    class Meta:
        model = DetallePaqueteServicio
        fields = ['id_detalle', 'id_paquete', 'id_servicio', 'servicio', 'precio', 'duracion_minutos', 'estado_servicio']


class PaqueteServicioSerializer(serializers.ModelSerializer):
    # Serializer del CU28: valida datos del paquete y servicios incluidos.
    servicios = serializers.PrimaryKeyRelatedField(
        queryset=Servicio.objects.filter(estado='ACTIVO'),
        many=True,
    )
    servicios_detalle = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = PaqueteServicio
        fields = [
            'id_paquete',
            'nombre',
            'descripcion',
            'precio_total',
            'duracion_minutos',
            'estado',
            'servicios',
            'servicios_detalle',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(DetallePaqueteServicioSerializer(many=True))
    def get_servicios_detalle(self, obj):
        # Devuelve informacion legible de cada servicio incluido en el paquete.
        detalles = obj.detalles_servicios.select_related('id_servicio').all()
        return DetallePaqueteServicioSerializer(detalles, many=True).data

    def validate_nombre(self, value):
        # El nombre del paquete es obligatorio y unico.
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del paquete no puede estar vacio.")

        duplicado = PaqueteServicio.objects.filter(nombre__iexact=nombre)
        if self.instance:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise serializers.ValidationError("Ya existe un paquete con ese nombre.")
        return nombre

    def validate_precio_total(self, value):
        # Regla de negocio: el precio total debe ser positivo.
        if value <= 0:
            raise serializers.ValidationError("El precio total debe ser mayor a 0.")
        return value

    def validate_duracion_minutos(self, value):
        # Regla de negocio: la duracion estimada debe ser positiva.
        if value <= 0:
            raise serializers.ValidationError("La duracion debe ser mayor a 0 minutos.")
        return value

    def validate_estado(self, value):
        # Solo acepta ACTIVO o INACTIVO para publicar u ocultar el paquete.
        estado = value.upper()
        if estado not in dict(PaqueteServicio.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_servicios(self, value):
        # Debe existir al menos un servicio activo dentro del paquete.
        if not value:
            raise serializers.ValidationError("Debe seleccionar al menos un servicio activo.")
        ids = [servicio.pk for servicio in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("No puede repetir servicios dentro del paquete.")
        servicios_inactivos = [servicio.nombre for servicio in value if servicio.estado != 'ACTIVO']
        if servicios_inactivos:
            raise serializers.ValidationError(f"Servicios inactivos no permitidos: {', '.join(servicios_inactivos)}.")
        return value

    def _actualizar_servicios(self, paquete, servicios):
        # Reemplaza la composicion del paquete por los servicios seleccionados.
        DetallePaqueteServicio.objects.filter(id_paquete=paquete).delete()
        DetallePaqueteServicio.objects.bulk_create([
            DetallePaqueteServicio(id_paquete=paquete, id_servicio=servicio)
            for servicio in servicios
        ])

    def create(self, validated_data):
        # CU28: primero crea el paquete y luego guarda los servicios que lo componen.
        servicios = validated_data.pop('servicios', [])
        paquete = PaqueteServicio.objects.create(**validated_data)
        self._actualizar_servicios(paquete, servicios)
        return paquete

    def update(self, instance, validated_data):
        # CU28: permite modificar datos generales y, si llegan servicios, reemplaza la lista incluida.
        servicios = validated_data.pop('servicios', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if servicios is not None:
            self._actualizar_servicios(instance, servicios)

        return instance


class DetalleProductoRecomendacionSerializer(serializers.ModelSerializer):
    # Representa los productos sugeridos dentro de una recomendacion.
    producto = serializers.CharField(source='id_producto.nombre', read_only=True)
    precio_venta = serializers.DecimalField(source='id_producto.precio_venta', max_digits=10, decimal_places=2, read_only=True)
    estado_producto = serializers.CharField(source='id_producto.estado', read_only=True)

    class Meta:
        model = DetalleProductoRecomendacion
        fields = ['id_detalle', 'id_recomendacion', 'id_producto', 'producto', 'precio_venta', 'estado_producto']


class RecomendacionCuidadoSerializer(serializers.ModelSerializer):
    # Serializer del CU29: registra recomendaciones posteriores a una atencion finalizada.
    id_atencion = serializers.PrimaryKeyRelatedField(
        queryset=AtencionServicio.objects.select_related('codigo_cliente', 'codigo_barbero', 'id_cita').all()
    )
    productos_sugeridos = serializers.PrimaryKeyRelatedField(
        queryset=Producto.objects.filter(estado='ACTIVO'),
        many=True,
        required=False,
    )
    productos_detalle = serializers.SerializerMethodField(read_only=True)
    cliente = serializers.SerializerMethodField(read_only=True)
    barbero = serializers.SerializerMethodField(read_only=True)
    servicio_principal = serializers.CharField(source='id_atencion.id_cita.id_servicio.nombre', read_only=True)
    fecha_atencion = serializers.DateField(source='id_atencion.fecha', read_only=True)
    codigo_cliente = serializers.PrimaryKeyRelatedField(read_only=True)
    codigo_barbero = serializers.PrimaryKeyRelatedField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = RecomendacionCuidado
        fields = [
            'id_recomendacion',
            'id_atencion',
            'codigo_cliente',
            'cliente',
            'codigo_barbero',
            'barbero',
            'servicio_principal',
            'fecha_atencion',
            'contenido',
            'frecuencia_corte',
            'cuidados_cabello',
            'productos_sugeridos',
            'productos_detalle',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['codigo_cliente', 'codigo_barbero', 'fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_cliente(self, obj):
        return f"{obj.codigo_cliente.nombre} {obj.codigo_cliente.apellido}".strip()

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    @extend_schema_field(DetalleProductoRecomendacionSerializer(many=True))
    def get_productos_detalle(self, obj):
        detalles = obj.detalles_productos.select_related('id_producto').all()
        return DetalleProductoRecomendacionSerializer(detalles, many=True).data

    def validate_contenido(self, value):
        # La recomendacion principal no puede estar vacia.
        contenido = value.strip()
        if not contenido:
            raise serializers.ValidationError("La recomendacion de cuidado es obligatoria.")
        return contenido

    def validate_estado(self, value):
        # CU29: controla si la recomendacion queda visible o inactiva para consultas posteriores.
        estado = value.upper()
        if estado not in dict(RecomendacionCuidado.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_productos_sugeridos(self, value):
        # Los productos son opcionales, pero si se envian deben estar activos y sin repetirse.
        ids = [producto.pk for producto in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("No puede repetir productos sugeridos.")
        productos_inactivos = [producto.nombre for producto in value if producto.estado != 'ACTIVO']
        if productos_inactivos:
            raise serializers.ValidationError(f"Productos inactivos no permitidos: {', '.join(productos_inactivos)}.")
        return value

    def validate(self, data):
        # La recomendacion solo puede registrarse sobre una atencion finalizada.
        instance = getattr(self, 'instance', None)
        atencion = data.get('id_atencion', getattr(instance, 'id_atencion', None))
        request = self.context.get('request')
        usuario_actual = getattr(request, 'usuario_actual', None) if request else None

        if not atencion:
            raise serializers.ValidationError({'id_atencion': 'Debe seleccionar una atencion finalizada.'})
        if atencion.estado != 'FINALIZADA':
            raise serializers.ValidationError({'id_atencion': 'La atencion no esta finalizada.'})
        if not atencion.codigo_cliente_id:
            raise serializers.ValidationError({'codigo_cliente': 'Cliente inexistente.'})

        if usuario_actual:
            # CU29: solo administradores o el barbero asignado a la atencion pueden registrar recomendaciones.
            if usuario_actual.es_cliente:
                raise serializers.ValidationError('El cliente no tiene permiso para registrar recomendaciones.')
            if usuario_actual.es_barbero and atencion.codigo_barbero_id != usuario_actual.codigo:
                raise serializers.ValidationError('El barbero solo puede recomendar sobre sus propias atenciones.')

        return data

    def _actualizar_productos(self, recomendacion, productos):
        # Reemplaza los productos sugeridos de la recomendacion.
        DetalleProductoRecomendacion.objects.filter(id_recomendacion=recomendacion).delete()
        DetalleProductoRecomendacion.objects.bulk_create([
            DetalleProductoRecomendacion(id_recomendacion=recomendacion, id_producto=producto)
            for producto in productos
        ])

    def create(self, validated_data):
        # CU29: toma cliente y barbero desde la atencion finalizada para evitar asociaciones manuales incorrectas.
        productos = validated_data.pop('productos_sugeridos', [])
        atencion = validated_data['id_atencion']
        recomendacion = RecomendacionCuidado.objects.create(
            codigo_cliente=atencion.codigo_cliente,
            codigo_barbero=atencion.codigo_barbero,
            **validated_data
        )
        self._actualizar_productos(recomendacion, productos)
        return recomendacion

    def update(self, instance, validated_data):
        # CU29: actualiza la recomendacion y sincroniza productos sugeridos cuando se envian.
        productos = validated_data.pop('productos_sugeridos', None)
        atencion = validated_data.get('id_atencion', instance.id_atencion)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.codigo_cliente = atencion.codigo_cliente
        instance.codigo_barbero = atencion.codigo_barbero
        instance.save()

        if productos is not None:
            self._actualizar_productos(instance, productos)

        return instance


class DiagnosticoCapilarSerializer(serializers.ModelSerializer):
    # Serializer del caso de uso Registrar diagnostico capilar del cliente.
    codigo_cliente = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='cliente')
    )
    id_cita = serializers.PrimaryKeyRelatedField(queryset=Cita.objects.select_related('codigo_cliente', 'codigo_barbero').all(), required=False, allow_null=True)
    id_atencion = serializers.PrimaryKeyRelatedField(queryset=AtencionServicio.objects.select_related('codigo_cliente', 'codigo_barbero', 'id_cita').all(), required=False, allow_null=True)
    codigo_barbero = serializers.PrimaryKeyRelatedField(read_only=True)
    cliente = serializers.SerializerMethodField(read_only=True)
    barbero = serializers.SerializerMethodField(read_only=True)
    servicio = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = DiagnosticoCapilar
        fields = [
            'id_diagnostico',
            'codigo_cliente',
            'cliente',
            'codigo_barbero',
            'barbero',
            'id_cita',
            'id_atencion',
            'servicio',
            'tipo_cabello',
            'condicion_cuero_cabelludo',
            'observaciones',
            'necesidades_detectadas',
            'cuidados_sugeridos',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['codigo_barbero', 'fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_cliente(self, obj):
        return f"{obj.codigo_cliente.nombre} {obj.codigo_cliente.apellido}".strip()

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_servicio(self, obj):
        cita = obj.id_cita or (obj.id_atencion.id_cita if obj.id_atencion_id else None)
        return cita.id_servicio.nombre if cita and cita.id_servicio_id else None

    def _validar_texto_obligatorio(self, value, mensaje):
        texto = value.strip()
        if not texto:
            raise serializers.ValidationError(mensaje)
        return texto

    def validate_tipo_cabello(self, value):
        return self._validar_texto_obligatorio(value, "El tipo de cabello es obligatorio.")

    def validate_condicion_cuero_cabelludo(self, value):
        return self._validar_texto_obligatorio(value, "La condicion del cuero cabelludo es obligatoria.")

    def validate_necesidades_detectadas(self, value):
        return self._validar_texto_obligatorio(value, "Las necesidades detectadas son obligatorias.")

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(DiagnosticoCapilar.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate(self, data):
        # El barbero autenticado registra el diagnostico sobre una cita o atencion real del cliente.
        request = self.context.get('request')
        usuario_actual = getattr(request, 'usuario_actual', None) if request else None
        instance = getattr(self, 'instance', None)
        cliente = data.get('codigo_cliente', getattr(instance, 'codigo_cliente', None))
        cita = data.get('id_cita', getattr(instance, 'id_cita', None))
        atencion = data.get('id_atencion', getattr(instance, 'id_atencion', None))

        if not usuario_actual or not usuario_actual.es_barbero:
            raise serializers.ValidationError('Usuario sin rol de barbero.')
        if not cliente or not cliente.es_cliente:
            raise serializers.ValidationError({'codigo_cliente': 'Cliente inexistente.'})
        if not cita and not atencion:
            raise serializers.ValidationError({'id_cita': 'Debe asociar una cita o atencion del cliente.'})
        if cita and cita.codigo_cliente_id != cliente.codigo:
            raise serializers.ValidationError({'id_cita': 'La cita no pertenece al cliente seleccionado.'})
        if cita and cita.codigo_barbero_id != usuario_actual.codigo:
            raise serializers.ValidationError({'id_cita': 'La cita no corresponde al barbero autenticado.'})
        if atencion and atencion.codigo_cliente_id != cliente.codigo:
            raise serializers.ValidationError({'id_atencion': 'La atencion no pertenece al cliente seleccionado.'})
        if atencion and atencion.codigo_barbero_id != usuario_actual.codigo:
            raise serializers.ValidationError({'id_atencion': 'La atencion no corresponde al barbero autenticado.'})
        if cita and atencion and atencion.id_cita_id != cita.id_cita:
            raise serializers.ValidationError({'id_atencion': 'La atencion no corresponde a la cita seleccionada.'})

        return data

    def create(self, validated_data):
        # El barbero se toma de la sesion para evitar que se suplante otro usuario.
        request = self.context.get('request')
        barbero = getattr(request, 'usuario_actual', None) if request else None
        return DiagnosticoCapilar.objects.create(codigo_barbero=barbero, **validated_data)


class TrabajoPortafolioSerializer(serializers.ModelSerializer):
    # Serializer del caso de uso Gestionar portafolio de trabajos realizados.
    id_servicio = serializers.PrimaryKeyRelatedField(queryset=Servicio.objects.filter(estado='ACTIVO'))
    id_atencion = serializers.PrimaryKeyRelatedField(queryset=AtencionServicio.objects.select_related('codigo_barbero').all(), required=False, allow_null=True)
    codigo_barbero = serializers.PrimaryKeyRelatedField(read_only=True)
    barbero = serializers.SerializerMethodField(read_only=True)
    servicio = serializers.CharField(source='id_servicio.nombre', read_only=True)
    imagen_url = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = TrabajoPortafolio
        fields = [
            'id_trabajo',
            'codigo_barbero',
            'barbero',
            'id_servicio',
            'servicio',
            'id_atencion',
            'descripcion',
            'estilo',
            'imagen',
            'imagen_url',
            'referencia',
            'estado',
            'observacion_revision',
            'revisado_por',
            'fecha_revision',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['codigo_barbero', 'revisado_por', 'fecha_revision', 'fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_imagen_url(self, obj):
        if not obj.imagen:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.imagen.url) if request else obj.imagen.url

    def _validar_texto(self, value, mensaje):
        texto = value.strip()
        if not texto:
            raise serializers.ValidationError(mensaje)
        return texto

    def validate_descripcion(self, value):
        return self._validar_texto(value, "La descripcion del trabajo es obligatoria.")

    def validate_estilo(self, value):
        return self._validar_texto(value, "El estilo del trabajo es obligatorio.")

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(TrabajoPortafolio.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_imagen(self, value):
        if not value:
            return value
        tipo = getattr(value, 'content_type', '') or ''
        if not tipo.startswith('image/'):
            raise serializers.ValidationError("Formato de imagen no valido. Debe subir un archivo de imagen.")
        return value

    def validate(self, data):
        request = self.context.get('request')
        usuario = getattr(request, 'usuario_actual', None) if request else None
        instance = getattr(self, 'instance', None)
        atencion = data.get('id_atencion', getattr(instance, 'id_atencion', None))

        if not usuario or not (usuario.es_barbero or usuario.es_admin):
            raise serializers.ValidationError('Usuario sin permisos.')
        if atencion:
            if atencion.estado != 'FINALIZADA':
                raise serializers.ValidationError({'id_atencion': 'La atencion asociada debe estar finalizada.'})
            if usuario.es_barbero and atencion.codigo_barbero_id != usuario.codigo:
                raise serializers.ValidationError({'id_atencion': 'La atencion no corresponde al barbero autenticado.'})

        if usuario.es_barbero:
            data['estado'] = 'PENDIENTE'
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        usuario = getattr(request, 'usuario_actual', None) if request else None
        return TrabajoPortafolio.objects.create(codigo_barbero=usuario, **validated_data)


class RevisionTrabajoPortafolioSerializer(serializers.Serializer):
    # Serializer para que el administrador apruebe o rechace trabajos del portafolio.
    estado = serializers.CharField(max_length=20)
    observacion_revision = serializers.CharField(required=False, allow_blank=True)

    ESTADOS_REVISION = ['APROBADO', 'RECHAZADO', 'INACTIVO']

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in self.ESTADOS_REVISION:
            raise serializers.ValidationError("Estado invalido para revision.")
        return estado

    def update(self, instance, validated_data):
        request = self.context.get('request')
        usuario = getattr(request, 'usuario_actual', None) if request else None
        return instance.cambiar_estado(
            validated_data['estado'],
            usuario=usuario,
            observacion=validated_data.get('observacion_revision', ''),
        )
