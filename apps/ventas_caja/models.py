from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.citas.models import Cita
from apps.inventario.models import Producto
from apps.seguridad.models import Usuario
from apps.servicios.models import Servicio


# Modelos del paquete Ventas y Caja.
# En este ciclo solo se implementan:
# - CU13 MetodoPago
# - CU14 PlanComision
# - CU18 Caja


class MetodoPago(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_metodo_pago = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    requiere_referencia = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ventas_caja_metodo_pago'
        verbose_name = 'Metodo de pago'
        verbose_name_plural = 'Metodos de pago'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def consultar(cls):
        return cls.objects.all()

    def guardar(self):
        self.save()
        return self

    def actualizar(self, **kwargs):
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        self.save()
        return self

    def cambiar_estado(self, estado):
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


class PlanComision(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_plan_comision = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    codigo_barbero = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='planes_comision'
    )
    porcentaje_barbero = models.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_barberia = models.DecimalField(max_digits=5, decimal_places=2)
    fecha_inicio = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ventas_caja_plan_comision'
        verbose_name = 'Plan de comision'
        verbose_name_plural = 'Planes de comision'
        ordering = ['-fecha_inicio', 'nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def consultar(cls):
        return cls.objects.select_related('codigo_barbero', 'codigo_barbero__id_rol').all()

    def guardar(self):
        self.save()
        return self

    def actualizar(self, **kwargs):
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        self.save()
        return self

    def cambiar_estado(self, estado):
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


class CampaniaFidelizacion(models.Model):
    # Gestionar campanias de fidelizacion para clientes frecuentes.
    TIPOS_CONDICION = (
        ('VISITAS', 'Cantidad de visitas'),
        ('SERVICIOS', 'Servicios acumulados'),
        ('MONTO', 'Monto acumulado'),
    )
    TIPOS_BENEFICIO = (
        ('DESCUENTO_PORCENTAJE', 'Descuento porcentual'),
        ('DESCUENTO_MONTO', 'Descuento por monto'),
        ('SERVICIO_GRATIS', 'Servicio gratis'),
        ('PRODUCTO_GRATIS', 'Producto gratis'),
    )
    ESTADOS = (
        ('PROGRAMADA', 'Programada'),
        ('ACTIVA', 'Activa'),
        ('INACTIVA', 'Inactiva'),
        ('FINALIZADA', 'Finalizada'),
    )

    id_campania = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    tipo_condicion = models.CharField(max_length=30, choices=TIPOS_CONDICION)
    valor_condicion = models.DecimalField(max_digits=12, decimal_places=2)
    tipo_beneficio = models.CharField(max_length=30, choices=TIPOS_BENEFICIO)
    valor_beneficio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    beneficio = models.TextField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PROGRAMADA')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    servicios_aplicables = models.ManyToManyField(
        Servicio,
        related_name='campanias_fidelizacion',
        blank=True,
    )

    class Meta:
        db_table = 'ventas_caja_campania_fidelizacion'
        verbose_name = 'Campania de fidelizacion'
        verbose_name_plural = 'Campanias de fidelizacion'
        ordering = ['-fecha_inicio', 'nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def consultar(cls):
        return cls.objects.prefetch_related('servicios_aplicables')

    def cambiar_estado(self, estado):
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


class Caja(models.Model):
    ESTADOS = (
        ('ABIERTA', 'Abierta'),
        ('CERRADA', 'Cerrada'),
    )

    id_caja = models.AutoField(primary_key=True)
    codigo_usuario_apertura = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_usuario_apertura',
        related_name='cajas_abiertas'
    )
    codigo_usuario_cierre = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_usuario_cierre',
        related_name='cajas_cerradas',
        null=True,
        blank=True
    )
    monto_apertura = models.DecimalField(max_digits=12, decimal_places=2)
    monto_cierre = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    saldo_esperado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    diferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    justificacion_cierre = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ABIERTA')
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ventas_caja_caja'
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'
        ordering = ['-fecha_apertura']
        constraints = [
            models.UniqueConstraint(
                fields=['estado'],
                condition=Q(estado='ABIERTA'),
                name='ventas_caja_unica_caja_abierta',
            )
        ]

    def __str__(self):
        return f"Caja {self.id_caja} - {self.estado}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related(
            'codigo_usuario_apertura',
            'codigo_usuario_apertura__id_rol',
            'codigo_usuario_cierre',
            'codigo_usuario_cierre__id_rol',
        ).all()

    @classmethod
    def caja_abierta(cls):
        return cls.consultar().filter(estado='ABIERTA').first()

    @property
    def ingresos(self):
        return self.movimientos.filter(tipo='INGRESO', estado='ACTIVO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    @property
    def egresos(self):
        return self.movimientos.filter(tipo='EGRESO', estado='ACTIVO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    @property
    def saldo_efectivo(self):
        ingresos = self.movimientos.filter(
            tipo='INGRESO',
            estado='ACTIVO',
            id_metodo_pago__nombre__iexact='EFECTIVO',
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        egresos = self.movimientos.filter(
            tipo='EGRESO',
            estado='ACTIVO',
            id_metodo_pago__nombre__iexact='EFECTIVO',
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        return self.monto_apertura + ingresos - egresos

    @property
    def saldo_actual(self):
        return self.monto_apertura + self.ingresos - self.egresos

    def recalcular_saldo_esperado(self):
        self.saldo_esperado = self.saldo_efectivo
        self.save(update_fields=['saldo_esperado', 'fecha_actualizacion'])
        return self

    def cerrar(self, usuario, monto_cierre, justificacion=''):
        self.recalcular_saldo_esperado()
        self.codigo_usuario_cierre = usuario
        self.monto_cierre = monto_cierre
        self.diferencia = monto_cierre - self.saldo_esperado
        self.justificacion_cierre = justificacion or ''
        self.estado = 'CERRADA'
        self.fecha_cierre = timezone.now()
        self.save(update_fields=[
            'codigo_usuario_cierre',
            'monto_cierre',
            'saldo_esperado',
            'diferencia',
            'justificacion_cierre',
            'estado',
            'fecha_cierre',
            'fecha_actualizacion',
        ])
        return self


class MovimientoCaja(models.Model):
    TIPOS_MOVIMIENTO = (
        ('INGRESO', 'Ingreso'),
        ('EGRESO', 'Egreso'),
    )
    TIPOS_DETALLE = (
        ('VENTA', 'Venta'),
        ('INGRESO_MANUAL', 'Ingreso manual'),
        ('EGRESO', 'Egreso'),
        ('RETIRO', 'Retiro'),
        ('DEVOLUCION', 'Devolucion'),
        ('AJUSTE_POSITIVO', 'Ajuste positivo'),
        ('AJUSTE_NEGATIVO', 'Ajuste negativo'),
    )
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('ANULADO', 'Anulado'),
    )

    id_movimiento_caja = models.AutoField(primary_key=True)
    caja = models.ForeignKey(
        Caja,
        on_delete=models.CASCADE,
        db_column='id_caja',
        related_name='movimientos'
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_MOVIMIENTO)
    tipo_movimiento = models.CharField(max_length=30, choices=TIPOS_DETALLE, default='INGRESO_MANUAL')
    naturaleza = models.CharField(max_length=20, choices=TIPOS_MOVIMIENTO, default='INGRESO')
    id_metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        db_column='id_metodo_pago',
        related_name='movimientos_caja',
        null=True,
        blank=True
    )
    id_venta = models.ForeignKey(
        'Venta',
        on_delete=models.SET_NULL,
        db_column='id_venta',
        related_name='movimientos_caja',
        null=True,
        blank=True
    )
    id_pago_venta = models.ForeignKey(
        'PagoVenta',
        on_delete=models.SET_NULL,
        db_column='id_pago_venta',
        related_name='movimientos_caja',
        null=True,
        blank=True
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    descripcion = models.TextField(blank=True)
    referencia = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    motivo_anulacion = models.TextField(blank=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        db_column='codigo_usuario',
        related_name='movimientos_caja',
        null=True,
        blank=True
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ventas_caja_movimiento_caja'
        verbose_name = 'Movimiento de caja'
        verbose_name_plural = 'Movimientos de caja'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.tipo} {self.monto} - Caja {self.caja_id}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related(
            'caja',
            'usuario',
            'usuario__id_rol',
            'id_metodo_pago',
            'id_venta',
            'id_pago_venta',
        ).all()


class Venta(models.Model):
    ESTADOS = (
        ('BORRADOR', 'Borrador'),
        ('PENDIENTE_PAGO', 'Pendiente de pago'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
    )

    id_venta = models.AutoField(primary_key=True)
    codigo_cliente = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_cliente',
        related_name='ventas_cliente',
        null=True,
        blank=True
    )
    id_cita = models.ForeignKey(
        Cita,
        on_delete=models.SET_NULL,
        db_column='id_cita',
        related_name='ventas',
        null=True,
        blank=True
    )
    codigo_cajero = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_cajero',
        related_name='ventas_registradas'
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='BORRADOR')
    observacion = models.TextField(blank=True)
    motivo_anulacion = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ventas_caja_venta'
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Venta {self.id_venta} - {self.estado}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related(
            'codigo_cliente',
            'codigo_cliente__id_rol',
            'codigo_cajero',
            'codigo_cajero__id_rol',
            'id_cita',
        ).prefetch_related('detalles', 'pagos', 'comisiones')

    def recalcular_totales(self):
        subtotal = self.detalles.aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')
        self.subtotal = subtotal
        self.total = max(subtotal - self.descuento, Decimal('0.00'))
        self.save(update_fields=['subtotal', 'total', 'fecha_actualizacion'])
        return self


class DetalleVenta(models.Model):
    TIPOS_ITEM = (
        ('PRODUCTO', 'Producto'),
        ('SERVICIO', 'Servicio'),
    )

    id_detalle = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        db_column='id_venta',
        related_name='detalles'
    )
    tipo_item = models.CharField(max_length=20, choices=TIPOS_ITEM)
    id_producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        db_column='id_producto',
        related_name='detalles_venta',
        null=True,
        blank=True
    )
    id_servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        db_column='id_servicio',
        related_name='detalles_venta',
        null=True,
        blank=True
    )
    codigo_barbero = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='servicios_vendidos',
        null=True,
        blank=True
    )
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'ventas_caja_detalle_venta'
        verbose_name = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'

    def __str__(self):
        return f"{self.tipo_item} - {self.subtotal}"


class PagoVenta(models.Model):
    ESTADOS = (
        ('REGISTRADO', 'Registrado'),
        ('ANULADO', 'Anulado'),
    )

    id_pago = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        db_column='id_venta',
        related_name='pagos'
    )
    id_metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        db_column='id_metodo_pago',
        related_name='pagos_venta'
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    referencia = models.CharField(max_length=150, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='REGISTRADO')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ventas_caja_pago_venta'
        verbose_name = 'Pago de venta'
        verbose_name_plural = 'Pagos de venta'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Pago {self.monto} - Venta {self.id_venta_id}"


class VentaCuotas(models.Model):
    # CU33: cabecera del plan de pagos asociado a una venta ya registrada.
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
    )

    id_venta_cuotas = models.AutoField(primary_key=True)
    id_venta = models.OneToOneField(
        Venta,
        on_delete=models.CASCADE,
        db_column='id_venta',
        related_name='venta_cuotas'
    )
    monto_inicial = models.DecimalField(max_digits=12, decimal_places=2)  # Importe cobrado al confirmar la venta.
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)  # Total restante que se divide en cuotas.
    cantidad_cuotas = models.PositiveIntegerField()  # Numero de cuotas pendientes generadas por el sistema.
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ventas_caja_venta_cuotas'
        verbose_name = 'Venta por cuotas'
        verbose_name_plural = 'Ventas por cuotas'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Venta cuotas #{self.id_venta_id} - {self.estado}"

    @classmethod
    def consultar(cls):
        # Consulta optimizada para listar la venta, cliente, cajero y detalle de cuotas.
        return cls.objects.select_related(
            'id_venta',
            'id_venta__codigo_cliente',
            'id_venta__codigo_cajero',
        ).prefetch_related('cuotas')


class CuotaVenta(models.Model):
    # CU33: cada registro representa una cuota individual con vencimiento y estado de pago.
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('VENCIDA', 'Vencida'),
        ('ANULADA', 'Anulada'),
    )

    id_cuota = models.AutoField(primary_key=True)
    id_venta_cuotas = models.ForeignKey(
        VentaCuotas,
        on_delete=models.CASCADE,
        db_column='id_venta_cuotas',
        related_name='cuotas'
    )
    numero_cuota = models.PositiveIntegerField()  # Orden de pago dentro del plan.
    monto = models.DecimalField(max_digits=12, decimal_places=2)  # Monto a cobrar en esta cuota.
    fecha_vencimiento = models.DateField()  # Fecha limite definida desde el primer vencimiento.
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    fecha_pago = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ventas_caja_cuota_venta'
        verbose_name = 'Cuota de venta'
        verbose_name_plural = 'Cuotas de venta'
        ordering = ['id_venta_cuotas', 'numero_cuota']
        unique_together = ('id_venta_cuotas', 'numero_cuota')

    def __str__(self):
        return f"Cuota {self.numero_cuota} - Venta {self.id_venta_cuotas_id}"


class PagoStripe(models.Model):
    ESTADOS = (
        ('CREADO', 'Creado'),
        ('REQUIERE_PAGO', 'Requiere pago'),
        ('PROCESANDO', 'Procesando'),
        ('EXITOSO', 'Exitoso'),
        ('FALLIDO', 'Fallido'),
        ('CANCELADO', 'Cancelado'),
    )

    id_pago_stripe = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        db_column='id_venta',
        related_name='pagos_stripe'
    )
    stripe_payment_intent_id = models.CharField(max_length=120, unique=True)
    client_secret = models.CharField(max_length=255, blank=True)
    stripe_status = models.CharField(max_length=50, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='CREADO')
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=10)
    raw_response = models.JSONField(default=dict, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ventas_caja_pago_stripe'
        verbose_name = 'Pago Stripe'
        verbose_name_plural = 'Pagos Stripe'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Stripe {self.stripe_payment_intent_id} - Venta {self.id_venta_id}"


class ComisionVenta(models.Model):
    ESTADOS_PAGO = (
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
    )

    id_comision = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        db_column='id_venta',
        related_name='comisiones'
    )
    id_detalle = models.ForeignKey(
        DetalleVenta,
        on_delete=models.CASCADE,
        db_column='id_detalle',
        related_name='comisiones'
    )
    codigo_barbero = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='comisiones_venta'
    )
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    estado_pago = models.CharField(max_length=20, choices=ESTADOS_PAGO, default='PENDIENTE')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ventas_caja_comision_venta'
        verbose_name = 'Comision de venta'
        verbose_name_plural = 'Comisiones de venta'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Comision {self.monto} - {self.codigo_barbero_id}"
