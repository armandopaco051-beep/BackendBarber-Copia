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
