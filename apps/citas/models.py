from django.db import models

from apps.seguridad.models import Usuario
from apps.servicios.models import Servicio


# Catalogo de estados que puede tener una cita.
# Tabla fisica existente: agenda.estado_cita.
class EstadoCita(models.Model):
    id_estado = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = '"agenda"."estado_cita"'
        verbose_name = 'Estado de cita'
        verbose_name_plural = 'Estados de cita'
        ordering = ['id_estado']

    def __str__(self):
        return self.nombre


# Tabla puente entre barberos y servicios.
# Sirve para validar la regla: "el barbero debe estar habilitado para realizar el servicio".
# Tabla fisica: agenda.barbero_servicio.
class BarberoServicio(models.Model):
    id_barbero_servicio = models.AutoField(primary_key=True)
    codigo_barbero = models.ForeignKey(
        # Barbero es un Usuario con rol Barbero.
        Usuario,
        on_delete=models.CASCADE,
        db_column='codigo_barbero',
        related_name='servicios_habilitados'
    )
    id_servicio = models.ForeignKey(
        # Servicio pertenece al paquete servicios y se guarda en agenda.servicio.
        Servicio,
        on_delete=models.CASCADE,
        db_column='id_servicio',
        related_name='barberos_habilitados'
    )
    estado = models.CharField(max_length=20, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        # unique_together evita repetir el mismo servicio para el mismo barbero.
        db_table = '"agenda"."barbero_servicio"'
        verbose_name = 'Servicio habilitado por barbero'
        verbose_name_plural = 'Servicios habilitados por barbero'
        ordering = ['codigo_barbero', 'id_servicio']
        unique_together = ('codigo_barbero', 'id_servicio')

    def __str__(self):
        return f"{self.codigo_barbero.codigo} - {self.id_servicio.nombre}"


# Modelo principal del CU11 Gestionar citas.
# Usa la tabla existente agenda.cita, extendida con cliente, barbero, servicio,
# hora_fin, observacion, motivo_cancelacion, precio_base y auditoria.
class Cita(models.Model):
    id_cita = models.AutoField(primary_key=True, db_column='codigo')
    codigo_cliente = models.ForeignKey(
        # Cliente es un Usuario con rol Cliente.
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_cliente',
        related_name='citas_cliente'
    )
    codigo_barbero = models.ForeignKey(
        # Barbero asignado a la cita.
        Usuario,
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='citas_barbero'
    )
    id_servicio = models.ForeignKey(
        # Servicio reservado; de aqui se toma precio y duracion.
        Servicio,
        on_delete=models.PROTECT,
        db_column='id_servicio',
        related_name='citas'
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField(db_column='hora')
    hora_fin = models.TimeField()
    id_estadoc = models.ForeignKey(
        # Estado actual de la cita: PENDIENTE, CONFIRMADA, FINALIZADA, etc.
        EstadoCita,
        on_delete=models.PROTECT,
        db_column='id_estadoc',
        related_name='citas'
    )
    observacion = models.TextField(blank=True)
    motivo_cancelacion = models.TextField(blank=True)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    registrado_por = models.ForeignKey(
        # Usuario administrador que registro la cita.
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='registrado_por',
        related_name='citas_registradas'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"agenda"."cita"'
        verbose_name = 'Cita'
        verbose_name_plural = 'Citas'
        ordering = ['-fecha', 'hora_inicio']

    def __str__(self):
        return f"{self.fecha} {self.hora_inicio} - {self.codigo_cliente.codigo}"


# Historial de cambios de estado de una cita.
# Permite defender trazabilidad: Pendiente -> Confirmada -> Finalizada, etc.
# Tabla fisica: agenda.historial_estado_cita.
class HistorialEstadoCita(models.Model):
    id_historial = models.AutoField(primary_key=True)
    id_cita = models.ForeignKey(
        Cita,
        on_delete=models.CASCADE,
        db_column='id_cita',
        related_name='historial_estados'
    )
    estado_anterior = models.ForeignKey(
        EstadoCita,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='estado_anterior',
        related_name='historiales_como_anterior'
    )
    estado_nuevo = models.ForeignKey(
        EstadoCita,
        on_delete=models.PROTECT,
        db_column='estado_nuevo',
        related_name='historiales_como_nuevo'
    )
    observacion = models.TextField(blank=True)
    fecha_cambio = models.DateTimeField(auto_now_add=True)
    cambiado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='cambiado_por',
        related_name='cambios_estado_cita'
    )

    class Meta:
        db_table = '"agenda"."historial_estado_cita"'
        verbose_name = 'Historial de estado de cita'
        verbose_name_plural = 'Historial de estados de cita'
        ordering = ['-fecha_cambio']

    def __str__(self):
        return f"Cita {self.id_cita_id}: {self.estado_nuevo.nombre}"
