from django.db import models

from apps.seguridad.models import Usuario


class CategoriaProducto(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_categoria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventario_categoria_producto'
        verbose_name = 'Categoria de producto'
        verbose_name_plural = 'Categorias de productos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def consultar(cls):
        return cls.objects.all()


class Marca(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_marca = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventario_marca'
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def consultar(cls):
        return cls.objects.all()


class Producto(models.Model):
    TIPOS_PRODUCTO = (
        ('VENTA', 'Venta'),
        ('USO_INTERNO', 'Uso interno'),
        ('AMBOS', 'Ambos'),
    )

    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_producto = models.AutoField(primary_key=True)
    id_categoria = models.ForeignKey(
        CategoriaProducto,
        on_delete=models.PROTECT,
        db_column='id_categoria',
        related_name='productos'
    )
    id_marca = models.ForeignKey(
        Marca,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='id_marca',
        related_name='productos'
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cantidad_disponible = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=0)
    tipo_producto = models.CharField(max_length=20, choices=TIPOS_PRODUCTO)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventario_producto'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def stock_bajo(self):
        return self.cantidad_disponible <= self.stock_minimo

    @classmethod
    def consultar(cls):
        return cls.objects.select_related('id_categoria', 'id_marca').all()


class Insumo(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_insumo = models.AutoField(primary_key=True)
    id_categoria = models.ForeignKey(
        CategoriaProducto,
        on_delete=models.PROTECT,
        db_column='id_categoria',
        related_name='insumos'
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    unidad_medida = models.CharField(max_length=50)
    cantidad_disponible = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventario_insumo'
        verbose_name = 'Insumo'
        verbose_name_plural = 'Insumos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def stock_bajo(self):
        return self.cantidad_disponible <= self.stock_minimo

    @classmethod
    def consultar(cls):
        return cls.objects.select_related('id_categoria').all()


class MovimientoInventario(models.Model):
    TIPOS_MOVIMIENTO = (
        ('ENTRADA_INICIAL', 'Entrada inicial'),
        ('AJUSTE', 'Ajuste'),
        ('ACTIVACION', 'Activacion'),
        ('DESACTIVACION', 'Desactivacion'),
    )

    id_movimiento = models.AutoField(primary_key=True)
    id_producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='id_producto',
        related_name='movimientos'
    )
    id_insumo = models.ForeignKey(
        Insumo,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='id_insumo',
        related_name='movimientos'
    )
    tipo_movimiento = models.CharField(max_length=20, choices=TIPOS_MOVIMIENTO)
    cantidad = models.PositiveIntegerField(default=0)
    motivo = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='codigo_usuario',
        related_name='movimientos_inventario'
    )

    class Meta:
        db_table = 'inventario_movimiento_inventario'
        verbose_name = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.tipo_movimiento} - {self.fecha}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related('id_producto', 'id_insumo', 'usuario').all()
