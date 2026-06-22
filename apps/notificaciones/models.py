from django.db import models

from apps.seguridad.models import Usuario


class PushSubscription(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='codigo_usuario',
        related_name='suscripciones_push'
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    navegador = models.CharField(max_length=255, blank=True)
    activa = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notificaciones_push_subscription'
        verbose_name = 'Suscripcion push'
        verbose_name_plural = 'Suscripciones push'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.usuario_id} - {self.activa}"


class Notificacion(models.Model):
    TIPOS = (
        ('PROMOCION', 'Promocion'),
        ('NUEVO_BARBERO', 'Nuevo barbero'),
        ('CITA', 'Cita'),
        ('RECORDATORIO_CITA', 'Recordatorio de cita'),
        ('INVENTARIO', 'Inventario'),
        ('SISTEMA', 'Sistema'),
    )
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('ENVIADA', 'Enviada'),
        ('PARCIAL', 'Parcial'),
        ('FALLIDA', 'Fallida'),
    )

    id_notificacion = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=30, choices=TIPOS)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    usuario_destino = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='usuario_destino',
        related_name='notificaciones_recibidas',
        null=True,
        blank=True
    )
    rol_destino = models.CharField(max_length=100, blank=True)
    enviada = models.BooleanField(default=False)
    estado_envio = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    enviados = models.PositiveIntegerField(default=0)
    fallidos = models.PositiveIntegerField(default=0)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notificaciones_notificacion'
        verbose_name = 'Notificacion'
        verbose_name_plural = 'Notificaciones'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.tipo} - {self.titulo}"


class NotificacionUsuario(models.Model):
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('ENVIADA', 'Enviada'),
        ('FALLIDA', 'Fallida'),
    )

    id_notificacion_usuario = models.AutoField(primary_key=True)
    notificacion = models.ForeignKey(
        Notificacion,
        on_delete=models.CASCADE,
        db_column='id_notificacion',
        related_name='destinatarios'
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='codigo_usuario',
        related_name='notificaciones_usuario'
    )
    leida = models.BooleanField(default=False)
    estado_envio = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    fecha_lectura = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notificaciones_notificacion_usuario'
        verbose_name = 'Notificacion de usuario'
        verbose_name_plural = 'Notificaciones de usuarios'
        ordering = ['-fecha_registro']
        unique_together = ('notificacion', 'usuario')

    def __str__(self):
        return f"{self.notificacion_id} - {self.usuario_id}"
