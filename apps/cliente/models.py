from django.db import models


# El paquete cliente tambien usa tablas existentes:
# - seguridad.usuario para el cliente autenticado.
# - agenda.cita para sus reservas.
# - agenda.servicio para servicios.
# - seguridad.horario_laboral para disponibilidad.


# Modelo del CU30 Gestionar encuesta de satisfaccion.
# Representa una encuesta que el administrador puede activar para clientes atendidos.
class EncuestaSatisfaccion(models.Model):
    ESTADOS = (
        ('BORRADOR', 'Borrador'),
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_encuesta = models.AutoField(primary_key=True)
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='BORRADOR')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"agenda"."encuesta_satisfaccion"'
        verbose_name = 'Encuesta de satisfaccion'
        verbose_name_plural = 'Encuestas de satisfaccion'
        ordering = ['-fecha_registro', 'titulo']

    def __str__(self):
        return self.titulo

    @classmethod
    def consultar(cls):
        # Precarga preguntas y opciones para responder la encuesta completa.
        return cls.objects.prefetch_related('preguntas__opciones')

    def cambiar_estado(self, estado):
        # Permite publicar o retirar una encuesta sin eliminarla fisicamente.
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


class PreguntaEncuesta(models.Model):
    TIPOS_RESPUESTA = (
        ('OPCION_UNICA', 'Opcion unica'),
        ('ESCALA', 'Escala'),
        ('TEXTO', 'Texto'),
    )

    id_pregunta = models.AutoField(primary_key=True)
    id_encuesta = models.ForeignKey(
        EncuestaSatisfaccion,
        on_delete=models.CASCADE,
        db_column='id_encuesta',
        related_name='preguntas'
    )
    texto = models.TextField()
    tipo_respuesta = models.CharField(max_length=20, choices=TIPOS_RESPUESTA, default='ESCALA')
    orden = models.PositiveIntegerField(default=1)
    obligatoria = models.BooleanField(default=True)

    class Meta:
        db_table = '"agenda"."pregunta_encuesta"'
        verbose_name = 'Pregunta de encuesta'
        verbose_name_plural = 'Preguntas de encuesta'
        ordering = ['id_encuesta', 'orden', 'id_pregunta']

    def __str__(self):
        return self.texto


class OpcionRespuestaEncuesta(models.Model):
    id_opcion = models.AutoField(primary_key=True)
    id_pregunta = models.ForeignKey(
        PreguntaEncuesta,
        on_delete=models.CASCADE,
        db_column='id_pregunta',
        related_name='opciones'
    )
    texto = models.CharField(max_length=150)
    valor = models.PositiveIntegerField(null=True, blank=True)
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = '"agenda"."opcion_respuesta_encuesta"'
        verbose_name = 'Opcion de respuesta de encuesta'
        verbose_name_plural = 'Opciones de respuesta de encuesta'
        ordering = ['id_pregunta', 'orden', 'id_opcion']

    def __str__(self):
        return self.texto


# Modelo del CU31 Gestionar reclamos y sugerencias.
# Permite que el cliente registre una solicitud y que el administrador haga seguimiento.
class ReclamoSugerencia(models.Model):
    TIPOS_SOLICITUD = (
        ('RECLAMO', 'Reclamo'),
        ('SUGERENCIA', 'Sugerencia'),
    )

    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('EN_REVISION', 'En revision'),
        ('REVISADO', 'Revisado'),
        ('RESUELTO', 'Resuelto'),
        ('CERRADO', 'Cerrado'),
        ('INACTIVO', 'Inactivo'),
    )

    id_solicitud = models.AutoField(primary_key=True)
    codigo_cliente = models.ForeignKey(
        # Cliente autenticado que registra el reclamo o sugerencia.
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_cliente',
        related_name='reclamos_sugerencias'
    )
    tipo_solicitud = models.CharField(max_length=20, choices=TIPOS_SOLICITUD)
    detalle = models.TextField()
    id_cita = models.ForeignKey(
        # Relacion opcional si el reclamo corresponde a una cita especifica.
        'citas.Cita',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_cita',
        related_name='reclamos_sugerencias'
    )
    id_servicio = models.ForeignKey(
        # Relacion opcional si la solicitud se refiere a un servicio especifico.
        'servicios.Servicio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_servicio',
        related_name='reclamos_sugerencias'
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    respuesta_admin = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"agenda"."reclamo_sugerencia"'
        verbose_name = 'Reclamo o sugerencia'
        verbose_name_plural = 'Reclamos y sugerencias'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.tipo_solicitud} - {self.codigo_cliente.codigo}"

    @classmethod
    def consultar(cls):
        # Carga cliente, cita y servicio para listados administrativos completos.
        return cls.objects.select_related(
            'codigo_cliente',
            'codigo_cliente__id_rol',
            'id_cita',
            'id_servicio',
        )

    def cambiar_estado(self, estado):
        # Actualiza el estado de seguimiento sin eliminar el registro.
        self.estado = estado
        self.save(update_fields=['estado', 'fecha_actualizacion'])
        return self


# Caso de uso: Responder encuesta de satisfaccion.
# Cabecera de respuestas enviadas por un cliente para una atencion finalizada.
class RespuestaEncuestaSatisfaccion(models.Model):
    id_respuesta = models.AutoField(primary_key=True)
    id_encuesta = models.ForeignKey(
        EncuestaSatisfaccion,
        on_delete=models.PROTECT,
        db_column='id_encuesta',
        related_name='respuestas'
    )
    id_atencion = models.ForeignKey(
        'citas.AtencionServicio',
        on_delete=models.PROTECT,
        db_column='id_atencion',
        related_name='respuestas_encuesta'
    )
    codigo_cliente = models.ForeignKey(
        'seguridad.Usuario',
        on_delete=models.PROTECT,
        db_column='codigo_cliente',
        related_name='respuestas_encuestas'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"agenda"."respuesta_encuesta_satisfaccion"'
        verbose_name = 'Respuesta de encuesta de satisfaccion'
        verbose_name_plural = 'Respuestas de encuestas de satisfaccion'
        ordering = ['-fecha_registro']
        unique_together = ('id_encuesta', 'id_atencion', 'codigo_cliente')

    def __str__(self):
        return f"Respuesta {self.id_respuesta} - {self.codigo_cliente.codigo}"

    @classmethod
    def consultar(cls):
        return cls.objects.select_related(
            'id_encuesta',
            'id_atencion',
            'codigo_cliente',
        ).prefetch_related('detalles')


class DetalleRespuestaEncuesta(models.Model):
    id_detalle = models.AutoField(primary_key=True)
    id_respuesta = models.ForeignKey(
        RespuestaEncuestaSatisfaccion,
        on_delete=models.CASCADE,
        db_column='id_respuesta',
        related_name='detalles'
    )
    id_pregunta = models.ForeignKey(
        PreguntaEncuesta,
        on_delete=models.PROTECT,
        db_column='id_pregunta',
        related_name='respuestas_detalle'
    )
    id_opcion = models.ForeignKey(
        OpcionRespuestaEncuesta,
        on_delete=models.PROTECT,
        db_column='id_opcion',
        related_name='respuestas_detalle',
        null=True,
        blank=True,
    )
    respuesta_texto = models.TextField(blank=True)
    valor = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = '"agenda"."detalle_respuesta_encuesta"'
        verbose_name = 'Detalle de respuesta de encuesta'
        verbose_name_plural = 'Detalles de respuestas de encuesta'
        ordering = ['id_respuesta', 'id_pregunta']
        unique_together = ('id_respuesta', 'id_pregunta')

    def __str__(self):
        return f"{self.id_respuesta_id} - {self.id_pregunta_id}"
