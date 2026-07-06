from django.db import models


# Modelo de CU6.
# Representa una categoria para ordenar servicios, por ejemplo: Cortes, Barba o Color.
# Tabla fisica: agenda.categoria.
class CategoriaServicio(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_categoria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        # Se usa agenda.categoria porque la base de datos ya maneja los servicios en agenda.
        db_table = '"agenda"."categoria"'
        verbose_name = 'Categoria de servicio'
        verbose_name_plural = 'Categorias de servicios'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


# Modelo de CU10.
# Representa un servicio de barberia con precio, duracion y estado.
# Tabla fisica: agenda.servicio.
class Servicio(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_servicio = models.AutoField(primary_key=True)
    id_categoria = models.ForeignKey(
        # Relaciona cada servicio con una categoria activa.
        CategoriaServicio,
        on_delete=models.PROTECT,
        db_column='id_categoria',
        related_name='servicios'
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    duracion_minutos = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        # Apunta a la tabla existente agenda.servicio, extendida para CU10.
        db_table = '"agenda"."servicio"'
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'
        ordering = ['id_categoria', 'nombre']

    def __str__(self):
        return f"{self.nombre} - {self.precio}"


# Modelo del CU28 Gestionar paquetes de servicios.
# Agrupa varios servicios activos en una oferta con precio y duracion total.
class PaqueteServicio(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_paquete = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)
    duracion_minutos = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    servicios = models.ManyToManyField(
        Servicio,
        through='DetallePaqueteServicio',
        related_name='paquetes',
        blank=True,
    )

    class Meta:
        # Se guarda en agenda porque los servicios base tambien viven en ese esquema.
        db_table = '"agenda"."paquete_servicio"'
        verbose_name = 'Paquete de servicio'
        verbose_name_plural = 'Paquetes de servicios'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def consultar(cls):
        # Carga los servicios incluidos para listar paquetes sin consultas repetidas.
        return cls.objects.prefetch_related('servicios')

    def cambiar_estado(self, estado):
        # Permite activar o inactivar el paquete sin borrarlo fisicamente.
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


class DetallePaqueteServicio(models.Model):
    # Tabla intermedia del CU28: cada fila representa un servicio dentro de un paquete.
    id_detalle = models.AutoField(primary_key=True)
    id_paquete = models.ForeignKey(
        PaqueteServicio,
        on_delete=models.CASCADE,
        db_column='id_paquete',
        related_name='detalles_servicios'
    )
    id_servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        db_column='id_servicio',
        related_name='detalles_paquetes'
    )

    class Meta:
        db_table = '"agenda"."detalle_paquete_servicio"'
        verbose_name = 'Detalle de paquete de servicio'
        verbose_name_plural = 'Detalles de paquetes de servicios'
        ordering = ['id_paquete', 'id_servicio']
        unique_together = ('id_paquete', 'id_servicio')

    def __str__(self):
        return f"{self.id_paquete.nombre} - {self.id_servicio.nombre}"


# Modelo del CU29 Gestionar recomendaciones de cuidado.
# Guarda las indicaciones posteriores a una atencion finalizada para un cliente.
class RecomendacionCuidado(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_recomendacion = models.AutoField(primary_key=True)
    id_atencion = models.ForeignKey(
        # Atencion finalizada que origina la recomendacion.
        'citas.AtencionServicio',
        on_delete=models.PROTECT,
        db_column='id_atencion',
        related_name='recomendaciones_cuidado'
    )
    codigo_cliente = models.ForeignKey(
        # Cliente atendido; se copia desde la atencion para facilitar consultas posteriores.
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_cliente',
        related_name='recomendaciones_recibidas'
    )
    codigo_barbero = models.ForeignKey(
        # Barbero que registro la recomendacion.
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='recomendaciones_realizadas'
    )
    contenido = models.TextField()
    frecuencia_corte = models.CharField(max_length=150, blank=True)
    cuidados_cabello = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    productos_sugeridos = models.ManyToManyField(
        'inventario.Producto',
        through='DetalleProductoRecomendacion',
        related_name='recomendaciones_cuidado',
        blank=True,
    )

    class Meta:
        db_table = '"agenda"."recomendacion_cuidado"'
        verbose_name = 'Recomendacion de cuidado'
        verbose_name_plural = 'Recomendaciones de cuidado'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Recomendacion {self.id_recomendacion} - {self.codigo_cliente.codigo}"

    @classmethod
    def consultar(cls):
        # Carga atencion, cliente, barbero y productos sugeridos para listados completos.
        return cls.objects.select_related(
            'id_atencion',
            'id_atencion__id_cita',
            'codigo_cliente',
            'codigo_barbero',
        ).prefetch_related('productos_sugeridos')

    def cambiar_estado(self, estado):
        # Permite ocultar la recomendacion sin eliminar el registro.
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


class DetalleProductoRecomendacion(models.Model):
    # Tabla intermedia del CU29: productos sugeridos dentro de una recomendacion.
    id_detalle = models.AutoField(primary_key=True)
    id_recomendacion = models.ForeignKey(
        RecomendacionCuidado,
        on_delete=models.CASCADE,
        db_column='id_recomendacion',
        related_name='detalles_productos'
    )
    id_producto = models.ForeignKey(
        'inventario.Producto',
        on_delete=models.PROTECT,
        db_column='id_producto',
        related_name='detalles_recomendaciones'
    )

    class Meta:
        db_table = '"agenda"."detalle_producto_recomendacion"'
        verbose_name = 'Detalle de producto recomendado'
        verbose_name_plural = 'Detalles de productos recomendados'
        ordering = ['id_recomendacion', 'id_producto']
        unique_together = ('id_recomendacion', 'id_producto')

    def __str__(self):
        return f"{self.id_recomendacion_id} - {self.id_producto.nombre}"


# Caso de uso: Registrar diagnostico capilar del cliente.
# Guarda informacion tecnica del cabello para futuras atenciones personalizadas.
class DiagnosticoCapilar(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_diagnostico = models.AutoField(primary_key=True)
    codigo_cliente = models.ForeignKey(
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_cliente',
        related_name='diagnosticos_capilares_recibidos'
    )
    codigo_barbero = models.ForeignKey(
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='diagnosticos_capilares_realizados'
    )
    id_cita = models.ForeignKey(
        'citas.Cita',
        on_delete=models.PROTECT,
        db_column='id_cita',
        related_name='diagnosticos_capilares',
        null=True,
        blank=True,
    )
    id_atencion = models.ForeignKey(
        'citas.AtencionServicio',
        on_delete=models.PROTECT,
        db_column='id_atencion',
        related_name='diagnosticos_capilares',
        null=True,
        blank=True,
    )
    tipo_cabello = models.CharField(max_length=120)
    condicion_cuero_cabelludo = models.CharField(max_length=180)
    observaciones = models.TextField(blank=True)
    necesidades_detectadas = models.TextField()
    cuidados_sugeridos = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"agenda"."diagnostico_capilar"'
        verbose_name = 'Diagnostico capilar'
        verbose_name_plural = 'Diagnosticos capilares'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Diagnostico {self.id_diagnostico} - {self.codigo_cliente.codigo}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related(
            'codigo_cliente',
            'codigo_barbero',
            'id_cita',
            'id_cita__id_servicio',
            'id_atencion',
            'id_atencion__id_cita',
        )

    def cambiar_estado(self, estado):
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


# Caso de uso: Gestionar portafolio de trabajos realizados.
# Registra trabajos de barberos y permite publicarlos cuando el administrador los aprueba.
class TrabajoPortafolio(models.Model):
    ESTADOS = (
        ('PENDIENTE', 'Pendiente de revision'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('INACTIVO', 'Inactivo'),
    )

    id_trabajo = models.AutoField(primary_key=True)
    codigo_barbero = models.ForeignKey(
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_barbero',
        related_name='trabajos_portafolio'
    )
    id_servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        db_column='id_servicio',
        related_name='trabajos_portafolio'
    )
    id_atencion = models.ForeignKey(
        'citas.AtencionServicio',
        on_delete=models.SET_NULL,
        db_column='id_atencion',
        related_name='trabajos_portafolio',
        null=True,
        blank=True,
    )
    descripcion = models.TextField()
    estilo = models.CharField(max_length=150)
    imagen = models.FileField(upload_to='portafolio/trabajos/', blank=True, null=True)
    referencia = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    observacion_revision = models.TextField(blank=True)
    revisado_por = models.ForeignKey(
        'seguridad.Usuario',
        on_delete=models.SET_NULL,
        db_column='revisado_por',
        related_name='trabajos_portafolio_revisados',
        null=True,
        blank=True,
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"agenda"."trabajo_portafolio"'
        verbose_name = 'Trabajo de portafolio'
        verbose_name_plural = 'Trabajos de portafolio'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.estilo} - {self.codigo_barbero.codigo}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related(
            'codigo_barbero',
            'id_servicio',
            'id_atencion',
            'revisado_por',
        )

    def cambiar_estado(self, estado, usuario=None, observacion=''):
        self.estado = estado
        if usuario:
            self.revisado_por = usuario
        if observacion:
            self.observacion_revision = observacion
        from django.utils import timezone
        self.fecha_revision = timezone.now()
        self.save(update_fields=['estado', 'revisado_por', 'observacion_revision', 'fecha_revision', 'fecha_actualizacion'])
        return self
