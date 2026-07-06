from drf_spectacular.utils import extend_schema_field
from django.utils import timezone
from rest_framework import serializers

from apps.seguridad.models import Usuario
from apps.servicios.models import Servicio

from .models import (
    Caja,
    CampaniaFidelizacion,
    ComisionVenta,
    DetalleVenta,
    CuotaVenta,
    MetodoPago,
    MovimientoCaja,
    PagoStripe,
    PagoVenta,
    PlanComision,
    Venta,
    VentaCuotas,
)


# Serializers del paquete Ventas y Caja.
# En este ciclo solo se implementan:
# - CU13 MetodoPago
# - CU14 PlanComision
# - CU18 Caja


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


class CampaniaFidelizacionSerializer(serializers.ModelSerializer):
    # Serializer del caso de uso Gestionar campanias de fidelizacion.
    servicios_aplicables = serializers.PrimaryKeyRelatedField(
        queryset=Servicio.objects.filter(estado='ACTIVO'),
        many=True,
        required=False,
    )
    servicios_detalle = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = CampaniaFidelizacion
        fields = [
            'id_campania',
            'nombre',
            'descripcion',
            'tipo_condicion',
            'valor_condicion',
            'tipo_beneficio',
            'valor_beneficio',
            'beneficio',
            'fecha_inicio',
            'fecha_fin',
            'estado',
            'servicios_aplicables',
            'servicios_detalle',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_servicios_detalle(self, obj):
        return [
            {
                'id_servicio': servicio.id_servicio,
                'nombre': servicio.nombre,
                'precio': servicio.precio,
                'estado': servicio.estado,
            }
            for servicio in obj.servicios_aplicables.all()
        ]

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError("El nombre de la campania es obligatorio.")
        duplicada = CampaniaFidelizacion.objects.filter(nombre__iexact=nombre)
        if self.instance:
            duplicada = duplicada.exclude(pk=self.instance.pk)
        if duplicada.exists():
            raise serializers.ValidationError("Ya existe una campania con ese nombre.")
        return nombre

    def validate_tipo_condicion(self, value):
        tipo = value.upper()
        if tipo not in dict(CampaniaFidelizacion.TIPOS_CONDICION):
            raise serializers.ValidationError("Condicion invalida.")
        return tipo

    def validate_tipo_beneficio(self, value):
        tipo = value.upper()
        if tipo not in dict(CampaniaFidelizacion.TIPOS_BENEFICIO):
            raise serializers.ValidationError("Tipo de beneficio invalido.")
        return tipo

    def validate_estado(self, value):
        estado = value.upper()
        if estado not in dict(CampaniaFidelizacion.ESTADOS):
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate_valor_condicion(self, value):
        if value <= 0:
            raise serializers.ValidationError("El valor de la condicion debe ser mayor a 0.")
        return value

    def validate_beneficio(self, value):
        beneficio = value.strip()
        if not beneficio:
            raise serializers.ValidationError("El beneficio debe estar definido.")
        return beneficio

    def validate_servicios_aplicables(self, value):
        ids = [servicio.pk for servicio in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("No puede repetir servicios aplicables.")
        return value

    def validate(self, data):
        # Valida condicion, beneficio y rango de fechas de la campania.
        instance = getattr(self, 'instance', None)
        fecha_inicio = data.get('fecha_inicio', getattr(instance, 'fecha_inicio', None))
        fecha_fin = data.get('fecha_fin', getattr(instance, 'fecha_fin', None))
        tipo_beneficio = data.get('tipo_beneficio', getattr(instance, 'tipo_beneficio', None))
        valor_beneficio = data.get('valor_beneficio', getattr(instance, 'valor_beneficio', None))

        if not fecha_inicio or not fecha_fin:
            raise serializers.ValidationError({'fecha_inicio': 'Debe definir fecha de inicio y fecha de fin.'})
        if fecha_fin < fecha_inicio:
            raise serializers.ValidationError({'fecha_fin': 'La fecha de fin no puede ser anterior a la fecha de inicio.'})
        if tipo_beneficio in ['DESCUENTO_PORCENTAJE', 'DESCUENTO_MONTO'] and (valor_beneficio is None or valor_beneficio <= 0):
            raise serializers.ValidationError({'valor_beneficio': 'Debe definir un valor de beneficio mayor a 0.'})
        if tipo_beneficio == 'DESCUENTO_PORCENTAJE' and valor_beneficio > 100:
            raise serializers.ValidationError({'valor_beneficio': 'El descuento porcentual no puede superar 100.'})

        if 'estado' not in data and not instance:
            data['estado'] = 'ACTIVA' if fecha_inicio <= timezone.localdate() <= fecha_fin else 'PROGRAMADA'
        return data

    def create(self, validated_data):
        servicios = validated_data.pop('servicios_aplicables', [])
        campania = CampaniaFidelizacion.objects.create(**validated_data)
        campania.servicios_aplicables.set(servicios)
        return campania

    def update(self, instance, validated_data):
        servicios = validated_data.pop('servicios_aplicables', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if servicios is not None:
            instance.servicios_aplicables.set(servicios)
        return instance


class MovimientoCajaSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField(read_only=True)
    metodo_pago_nombre = serializers.CharField(source='id_metodo_pago.nombre', read_only=True, allow_null=True)

    class Meta:
        model = MovimientoCaja
        fields = [
            'id_movimiento_caja',
            'caja',
            'tipo',
            'tipo_movimiento',
            'naturaleza',
            'id_metodo_pago',
            'metodo_pago_nombre',
            'id_venta',
            'id_pago_venta',
            'monto',
            'descripcion',
            'referencia',
            'estado',
            'motivo_anulacion',
            'usuario',
            'usuario_nombre',
            'fecha',
        ]
        read_only_fields = ['fecha']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return f"{obj.usuario.nombre} {obj.usuario.apellido}".strip()

    def validate_tipo(self, value):
        tipo = value.upper()
        if tipo not in dict(MovimientoCaja.TIPOS_MOVIMIENTO):
            raise serializers.ValidationError("Tipo de movimiento invalido.")
        return tipo

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto del movimiento debe ser mayor a 0.")
        return value


class CajaSerializer(serializers.ModelSerializer):
    usuario_apertura_nombre = serializers.SerializerMethodField(read_only=True)
    usuario_cierre_nombre = serializers.SerializerMethodField(read_only=True)
    ingresos = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    egresos = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    saldo_actual = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    saldo_efectivo = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    movimientos = MovimientoCajaSerializer(many=True, read_only=True)

    class Meta:
        model = Caja
        fields = [
            'id_caja',
            'codigo_usuario_apertura',
            'usuario_apertura_nombre',
            'codigo_usuario_cierre',
            'usuario_cierre_nombre',
            'monto_apertura',
            'monto_cierre',
            'saldo_esperado',
            'diferencia',
            'justificacion_cierre',
            'estado',
            'fecha_apertura',
            'fecha_cierre',
            'fecha_actualizacion',
            'ingresos',
            'egresos',
            'saldo_actual',
            'saldo_efectivo',
            'movimientos',
        ]
        read_only_fields = [
            'codigo_usuario_apertura',
            'codigo_usuario_cierre',
            'monto_cierre',
            'saldo_esperado',
            'diferencia',
            'justificacion_cierre',
            'estado',
            'fecha_apertura',
            'fecha_cierre',
            'fecha_actualizacion',
        ]

    @extend_schema_field(serializers.CharField())
    def get_usuario_apertura_nombre(self, obj):
        if not obj.codigo_usuario_apertura:
            return None
        return f"{obj.codigo_usuario_apertura.nombre} {obj.codigo_usuario_apertura.apellido}".strip()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_usuario_cierre_nombre(self, obj):
        if not obj.codigo_usuario_cierre:
            return None
        return f"{obj.codigo_usuario_cierre.nombre} {obj.codigo_usuario_cierre.apellido}".strip()


class CajaAperturaSerializer(serializers.Serializer):
    monto_apertura = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_monto_apertura(self, value):
        if value < 0:
            raise serializers.ValidationError("El monto de apertura no puede ser negativo.")
        return value

    def validate(self, data):
        if Caja.objects.filter(estado='ABIERTA').exists():
            raise serializers.ValidationError("Ya existe una caja abierta.")
        return data


class CajaCierreSerializer(serializers.Serializer):
    monto_cierre = serializers.DecimalField(max_digits=12, decimal_places=2)
    justificacion_cierre = serializers.CharField(required=False, allow_blank=True)

    def validate_monto_cierre(self, value):
        if value < 0:
            raise serializers.ValidationError("El monto de cierre no puede ser negativo.")
        return value

    def validate(self, data):
        caja = self.context.get('caja')
        if not caja:
            raise serializers.ValidationError("No existe una caja abierta para cerrar.")
        if caja.estado != 'ABIERTA':
            raise serializers.ValidationError("La caja ya se encuentra cerrada.")

        caja.recalcular_saldo_esperado()
        monto_cierre = data.get('monto_cierre')
        justificacion = (data.get('justificacion_cierre') or '').strip()

        if monto_cierre < caja.saldo_esperado and not justificacion:
            raise serializers.ValidationError({
                'justificacion_cierre': 'Debe justificar cuando el monto de cierre es menor al saldo esperado.'
            })

        data['justificacion_cierre'] = justificacion
        return data


class MovimientoCajaCrearSerializer(serializers.Serializer):
    tipo_movimiento = serializers.ChoiceField(choices=[
        'INGRESO_MANUAL',
        'EGRESO',
        'RETIRO',
        'AJUSTE_POSITIVO',
        'AJUSTE_NEGATIVO',
    ])
    id_metodo_pago = serializers.IntegerField(required=False)
    monto = serializers.DecimalField(max_digits=12, decimal_places=2)
    descripcion = serializers.CharField()
    referencia = serializers.CharField(required=False, allow_blank=True)

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto del movimiento debe ser mayor a 0.")
        return value

    def validate_descripcion(self, value):
        descripcion = value.strip()
        if not descripcion:
            raise serializers.ValidationError("La descripcion o concepto es obligatorio.")
        return descripcion


class MovimientoCajaAnularSerializer(serializers.Serializer):
    motivo = serializers.CharField()

    def validate_motivo(self, value):
        motivo = value.strip()
        if not motivo:
            raise serializers.ValidationError("El motivo de anulacion es obligatorio.")
        return motivo


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='id_producto.nombre', read_only=True, allow_null=True)
    servicio_nombre = serializers.CharField(source='id_servicio.nombre', read_only=True, allow_null=True)
    barbero_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DetalleVenta
        fields = [
            'id_detalle',
            'tipo_item',
            'id_producto',
            'producto_nombre',
            'id_servicio',
            'servicio_nombre',
            'codigo_barbero',
            'barbero_nombre',
            'cantidad',
            'precio_unitario',
            'descuento',
            'subtotal',
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_barbero_nombre(self, obj):
        if not obj.codigo_barbero:
            return None
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()


class PagoVentaSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='id_metodo_pago.nombre', read_only=True)

    class Meta:
        model = PagoVenta
        fields = [
            'id_pago',
            'id_metodo_pago',
            'metodo_pago_nombre',
            'monto',
            'referencia',
            'estado',
            'fecha_registro',
        ]
        read_only_fields = ['estado', 'fecha_registro']


class PagoStripeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoStripe
        fields = [
            'id_pago_stripe',
            'id_venta',
            'stripe_payment_intent_id',
            'client_secret',
            'stripe_status',
            'estado',
            'amount',
            'currency',
            'fecha_creacion',
            'fecha_confirmacion',
            'fecha_actualizacion',
        ]
        read_only_fields = fields


class ComisionVentaSerializer(serializers.ModelSerializer):
    barbero_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ComisionVenta
        fields = [
            'id_comision',
            'id_detalle',
            'codigo_barbero',
            'barbero_nombre',
            'porcentaje',
            'monto',
            'estado_pago',
            'fecha_registro',
        ]
        read_only_fields = ['fecha_registro']

    @extend_schema_field(serializers.CharField())
    def get_barbero_nombre(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()


class VentaSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.SerializerMethodField(read_only=True)
    cajero_nombre = serializers.SerializerMethodField(read_only=True)
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    pagos = PagoVentaSerializer(many=True, read_only=True)
    pagos_stripe = PagoStripeSerializer(many=True, read_only=True)
    comisiones = ComisionVentaSerializer(many=True, read_only=True)

    class Meta:
        model = Venta
        fields = [
            'id_venta',
            'codigo_cliente',
            'cliente_nombre',
            'id_cita',
            'codigo_cajero',
            'cajero_nombre',
            'subtotal',
            'descuento',
            'total',
            'estado',
            'observacion',
            'motivo_anulacion',
            'fecha_registro',
            'fecha_actualizacion',
            'detalles',
            'pagos',
            'pagos_stripe',
            'comisiones',
        ]
        read_only_fields = [
            'codigo_cajero',
            'subtotal',
            'total',
            'estado',
            'motivo_anulacion',
            'fecha_registro',
            'fecha_actualizacion',
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_cliente_nombre(self, obj):
        if not obj.codigo_cliente:
            return None
        return f"{obj.codigo_cliente.nombre} {obj.codigo_cliente.apellido}".strip()

    @extend_schema_field(serializers.CharField())
    def get_cajero_nombre(self, obj):
        return f"{obj.codigo_cajero.nombre} {obj.codigo_cajero.apellido}".strip()


class DetalleVentaInputSerializer(serializers.Serializer):
    tipo_item = serializers.ChoiceField(choices=['PRODUCTO', 'SERVICIO'])
    id_producto = serializers.IntegerField(required=False)
    id_servicio = serializers.IntegerField(required=False)
    codigo_barbero = serializers.CharField(required=False, allow_blank=True)
    cantidad = serializers.IntegerField(min_value=1, default=1)
    descuento = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)

    def validate_descuento(self, value):
        if value < 0:
            raise serializers.ValidationError("El descuento no puede ser negativo.")
        return value

    def validate(self, data):
        tipo_item = data.get('tipo_item')
        if tipo_item == 'PRODUCTO' and not data.get('id_producto'):
            raise serializers.ValidationError({'id_producto': 'El producto es obligatorio para un detalle PRODUCTO.'})
        if tipo_item == 'SERVICIO':
            if not data.get('id_servicio'):
                raise serializers.ValidationError({'id_servicio': 'El servicio es obligatorio para un detalle SERVICIO.'})
            if not data.get('codigo_barbero'):
                raise serializers.ValidationError({'codigo_barbero': 'El barbero es obligatorio para un detalle SERVICIO.'})
        return data


class VentaCrearSerializer(serializers.Serializer):
    codigo_cliente = serializers.CharField(required=False, allow_blank=True)
    id_cita = serializers.IntegerField(required=False)
    descuento = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    observacion = serializers.CharField(required=False, allow_blank=True)
    detalles = DetalleVentaInputSerializer(many=True, required=False)

    def validate_descuento(self, value):
        if value < 0:
            raise serializers.ValidationError("El descuento no puede ser negativo.")
        return value

    def validate_detalles(self, value):
        return value

    def validate(self, data):
        if not data.get('id_cita') and not data.get('detalles'):
            raise serializers.ValidationError({'detalles': 'La venta debe tener detalles o estar vinculada a una cita.'})
        return data


class PagoVentaInputSerializer(serializers.Serializer):
    id_metodo_pago = serializers.IntegerField()
    monto = serializers.DecimalField(max_digits=12, decimal_places=2)
    referencia = serializers.CharField(required=False, allow_blank=True)

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto del pago debe ser mayor a 0.")
        return value


class VentaConfirmarSerializer(serializers.Serializer):
    pagos = PagoVentaInputSerializer(many=True)

    def validate_pagos(self, value):
        if not value:
            raise serializers.ValidationError("Debe registrar al menos un pago.")
        return value


class VentaAnularSerializer(serializers.Serializer):
    motivo = serializers.CharField()

    def validate_motivo(self, value):
        motivo = value.strip()
        if not motivo:
            raise serializers.ValidationError("El motivo de anulacion es obligatorio.")
        return motivo


class CuotaVentaSerializer(serializers.ModelSerializer):
    # CU33: expone cada cuota generada para consultar monto, vencimiento y estado.
    class Meta:
        model = CuotaVenta
        fields = [
            'id_cuota',
            'numero_cuota',
            'monto',
            'fecha_vencimiento',
            'estado',
            'fecha_pago',
        ]


class VentaCuotasSerializer(serializers.ModelSerializer):
    # CU33: respuesta completa de la venta por cuotas con venta base y cuotas pendientes.
    venta = VentaSerializer(source='id_venta', read_only=True)
    cuotas = CuotaVentaSerializer(many=True, read_only=True)

    class Meta:
        model = VentaCuotas
        fields = [
            'id_venta_cuotas',
            'id_venta',
            'venta',
            'monto_inicial',
            'saldo_pendiente',
            'cantidad_cuotas',
            'estado',
            'fecha_registro',
            'fecha_actualizacion',
            'cuotas',
        ]


class VentaCuotasCrearSerializer(VentaCrearSerializer):
    # CU33: datos adicionales que convierten una venta normal en venta financiada por cuotas.
    monto_inicial = serializers.DecimalField(max_digits=12, decimal_places=2)
    cantidad_cuotas = serializers.IntegerField(min_value=1)
    id_metodo_pago_inicial = serializers.IntegerField()
    referencia_inicial = serializers.CharField(required=False, allow_blank=True)
    fecha_primer_vencimiento = serializers.DateField()
    dias_entre_cuotas = serializers.IntegerField(min_value=1, default=30)

    def validate_monto_inicial(self, value):
        # CU33: el pago inicial debe existir y luego se compara contra el total calculado.
        if value <= 0:
            raise serializers.ValidationError("El monto inicial debe ser mayor a 0.")
        return value

    def validate(self, data):
        # CU33: reutiliza validaciones de venta y exige cliente directo o derivado de cita.
        data = super().validate(data)
        if not data.get('codigo_cliente') and not data.get('id_cita'):
            raise serializers.ValidationError({'codigo_cliente': 'Debe asociar un cliente a la venta por cuotas.'})
        return data
