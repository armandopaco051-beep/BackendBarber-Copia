from tabnanny import verbose
from django.db import models

# Create your models here.

class Rol(models.Model) : 
    # tabla de seguridad rol , roles de sistema : administrador, barbero , cliente 
    #usando en CU4 GESTION DE ROLES 
    id = models.AutoField(primary_key = True)
    nombre = models.CharField(max_length = 100) 

    class Meta :
        db_table = '"seguridad"."rol"'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
    
    def __str__(self):
        return self.nombre

class Usuario(models.Model): 
    #tabla de seguridad de usuario , usuariios crea un sistema (admin, barbero, cliente)
    codigo = models.CharField(max_length= 100, primary_key = True)
    nombre = models.CharField(max_length = 250)
    apellido = models.CharField(max_length= 250)
    telefono = models.CharField(max_length = 10)
    correo = models.CharField(max_length= 100)
    especialidad = models.CharField(max_length=100, null=True, blank=True)
    password  = models.CharField(max_length = 128)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    codigo_recuperacion = models.CharField(max_length=128, null=True, blank=True)
    codigo_recuperacion_expira = models.DateTimeField(null=True, blank=True)
    id_rol  = models.ForeignKey(Rol, on_delete=models.CASCADE, db_column = 'id_rol',related_name='usuarios')
    class Meta: 
        db_table = '"seguridad"."usuario"'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
    
    def __str__(self):
        return f"{self.nombre}{self.apellido}({self.codigo})"

    @property
    def rol_nombre(self) : 
        return self.id_rol.nombre if self.id_rol else None 

    @property
    def is_authenticated(self):
        return True

    @property
    def es_admin(self):
        return self.id_rol.nombre.lower() == 'administrador'
 
    @property
    def es_barbero(self):
        return self.id_rol.nombre.lower() == 'barbero'
 
    @property
    def es_cliente(self):
        return self.id_rol.nombre.lower() == 'cliente'


class Bitacora(models.Model):
    id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='codigo_usuario',
        related_name='bitacoras'
    )
    accion = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    metodo = models.CharField(max_length=10, blank=True)
    ruta = models.CharField(max_length=255, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"seguridad"."bitacora"'
        verbose_name = 'Bitacora'
        verbose_name_plural = 'Bitacoras'
        ordering = ['-fecha']

    def __str__(self):
        usuario = self.usuario.codigo if self.usuario else 'anonimo'
        return f"{self.fecha} - {usuario} - {self.accion}"


class HorarioLaboral(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    DIAS_SEMANA = (
        ('LUNES', 'Lunes'),
        ('MARTES', 'Martes'),
        ('MIERCOLES', 'Miercoles'),
        ('JUEVES', 'Jueves'),
        ('VIERNES', 'Viernes'),
        ('SABADO', 'Sabado'),
        ('DOMINGO', 'Domingo'),
    )

    id_horario = models.AutoField(primary_key=True)
    codigo_barbero = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='codigo_barbero',
        related_name='horarios_laborales'
    )
    dia_semana = models.CharField(max_length=15, choices=DIAS_SEMANA)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    hora_inicio_descanso = models.TimeField(null=True, blank=True)
    hora_fin_descanso = models.TimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    observacion = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"seguridad"."horario_laboral"'
        verbose_name = 'Horario laboral'
        verbose_name_plural = 'Horarios laborales'
        ordering = ['codigo_barbero', 'dia_semana', 'hora_inicio']

    def __str__(self):
        return f"{self.codigo_barbero.codigo} {self.dia_semana} {self.hora_inicio}-{self.hora_fin}"


class BloqueoHorario(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    )

    id_bloqueo = models.AutoField(primary_key=True)
    codigo_barbero = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='codigo_barbero',
        related_name='bloqueos_horario'
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"seguridad"."bloqueo_horario"'
        verbose_name = 'Bloqueo de horario'
        verbose_name_plural = 'Bloqueos de horario'
        ordering = ['-fecha', 'hora_inicio']

    def __str__(self):
        return f"{self.codigo_barbero.codigo} {self.fecha} {self.hora_inicio}-{self.hora_fin}"


class AsistenciaBarbero(models.Model):
    ESTADOS = (
        ('PRESENTE', 'Presente'),
        ('TARDE', 'Tarde'),
        ('AUSENTE', 'Ausente'),
        ('PERMISO', 'Permiso'),
        ('INHABILITADO', 'Inhabilitado'),
    )

    id_asistencia = models.AutoField(primary_key=True)
    codigo_barbero = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='codigo_barbero',
        related_name='asistencias'
    )
    fecha = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS)
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    observacion = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"seguridad"."asistencia_barbero"'
        verbose_name = 'Asistencia de barbero'
        verbose_name_plural = 'Asistencias de barberos'
        ordering = ['-fecha', 'codigo_barbero']
        unique_together = ('codigo_barbero', 'fecha')

    def __str__(self):
        return f"{self.codigo_barbero.codigo} {self.fecha} {self.estado}"
 
