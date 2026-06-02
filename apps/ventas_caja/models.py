from django.db import models

from apps.seguridad.models import Usuario


# Modelos del paquete Ventas y Caja.
# En este ciclo solo se implementan:
# - CU13 MetodoPago
# - CU14 PlanComision


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
