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
    password  = models.CharField(max_length = 128)
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
 
