from django.contrib.auth.hashers import check_password, make_password
from rest_framework import serializers

from apps.seguridad.models import Usuario


# Serializer para mostrar y actualizar el perfil del usuario autenticado.
# Este serializer NO permite cambiar codigo, rol ni permisos porque eso solo
# debe hacerlo el administrador desde el CRUD de usuarios.
class PerfilUsuarioSerializer(serializers.ModelSerializer):
    rol = serializers.CharField(source='id_rol.nombre', read_only=True)

    class Meta:
        model = Usuario
        fields = [
            'codigo',
            'nombre',
            'apellido',
            'telefono',
            'correo',
            'especialidad',
            'rol',
        ]
        read_only_fields = ['codigo', 'especialidad', 'rol']

    def validate_telefono(self, value):
        # Valida que el telefono sea numerico y no pase el largo definido en la tabla.
        if not value.isdigit():
            raise serializers.ValidationError("El telefono debe contener solo digitos.")
        if len(value) > 10:
            raise serializers.ValidationError("El telefono no puede exceder 10 digitos.")
        return value

    def validate_correo(self, value):
        # Evita que dos usuarios tengan el mismo correo electronico.
        correo = value.lower()
        queryset = Usuario.objects.filter(correo__iexact=correo)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return correo


# Serializer para cambiar la contrasena desde el perfil.
# Este flujo se usa cuando el usuario SI inicio sesion y conoce su contrasena actual.
class CambiarPasswordPerfilSerializer(serializers.Serializer):
    password_actual = serializers.CharField(write_only=True)
    nueva_password = serializers.CharField(write_only=True, min_length=6)
    confirmar_password = serializers.CharField(write_only=True, min_length=6)

    def validate_password_actual(self, value):
        # Compara la contrasena recibida con el hash guardado en la base de datos.
        usuario = self.context.get('usuario')
        if not usuario or not check_password(value, usuario.password):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate(self, data):
        # Confirma que la nueva contrasena coincida y que sea distinta a la actual.
        if data['nueva_password'] != data['confirmar_password']:
            raise serializers.ValidationError({"confirmar_password": "Las contraseñas no coinciden."})
        if data['password_actual'] == data['nueva_password']:
            raise serializers.ValidationError({"nueva_password": "La nueva contraseña debe ser diferente a la actual."})
        return data

    def save(self, **kwargs):
        # Guarda la nueva contrasena encriptada en seguridad.usuario.password.
        usuario = self.context['usuario']
        usuario.password = make_password(self.validated_data['nueva_password'])
        usuario.save(update_fields=['password'])
        return usuario
