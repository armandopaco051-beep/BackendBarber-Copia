from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.seguridad.models import Usuario


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
        return self.movimientos.filter(tipo='INGRESO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    @property
    def egresos(self):
        return self.movimientos.filter(tipo='EGRESO').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    @property
    def saldo_actual(self):
        return self.monto_apertura + self.ingresos - self.egresos

    def recalcular_saldo_esperado(self):
        self.saldo_esperado = self.saldo_actual
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

    id_movimiento_caja = models.AutoField(primary_key=True)
    caja = models.ForeignKey(
        Caja,
        on_delete=models.CASCADE,
        db_column='id_caja',
        related_name='movimientos'
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_MOVIMIENTO)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    descripcion = models.TextField(blank=True)
    referencia = models.CharField(max_length=100, blank=True)
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
        return cls.objects.select_related('caja', 'usuario', 'usuario__id_rol').all()
