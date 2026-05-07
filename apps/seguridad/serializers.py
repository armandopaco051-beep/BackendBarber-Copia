from rest_framework import serializers
from django.contrib.auth.hashers import make_password, check_password
from .models import Rol, Usuario


# ─────────────────────────────────────────────────────────────────────────────
# CU4 — Gestionar Roles
# ─────────────────────────────────────────────────────────────────────────────

class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ['id', 'nombre']

    def validate_nombre(self, value):
        if not value.strip():
            raise serializers.ValidationError("El nombre del rol no puede estar vacío.")
        return value.strip()


# ─────────────────────────────────────────────────────────────────────────────
# CU1 — Iniciar Sesión
# ─────────────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    correo = serializers.EmailField(max_length=100)
    password = serializers.CharField(max_length=100, write_only=True)

    def validate(self, data):
        correo = data.get('correo')
        password = data.get('password')

        try:
            usuario = Usuario.objects.select_related('id_rol').get(correo__iexact=correo)
        except Usuario.DoesNotExist:
            raise serializers.ValidationError("Credenciales incorrectas.")
        except Usuario.MultipleObjectsReturned:
            raise serializers.ValidationError("Existe mas de un usuario con este correo.")

        if not check_password(password, usuario.password):
            raise serializers.ValidationError("Credenciales incorrectas.")

        data['usuario'] = usuario
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


# ─────────────────────────────────────────────────────────────────────────────
# CU3 — Gestionar Usuarios (lectura general)
# ─────────────────────────────────────────────────────────────────────────────

class UsuarioListSerializer(serializers.ModelSerializer):
    rol = serializers.CharField(source='id_rol.nombre', read_only=True)
    id_rol = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.all()
    )

    class Meta:
        model = Usuario
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'id_rol', 'rol']


class UsuarioCrearSerializer(serializers.ModelSerializer):
    id_rol = serializers.PrimaryKeyRelatedField(queryset=Rol.objects.all())
    correo = serializers.EmailField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = Usuario
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'password', 'id_rol']

    def validate_codigo(self, value):
        if not value.strip():
            raise serializers.ValidationError("El código no puede estar vacío.")
        return value.strip()

    def validate_telefono(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("El teléfono debe contener solo dígitos.")
        if len(value) > 10:
            raise serializers.ValidationError("El teléfono no puede exceder 10 dígitos.")
        return value

    def validate_correo(self, value):
        correo = value.lower()
        if Usuario.objects.filter(correo__iexact=correo).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return correo

    def create(self, validated_data):
        # Hashear la contraseña antes de guardar
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


class UsuarioActualizarSerializer(serializers.ModelSerializer):
    id_rol = serializers.PrimaryKeyRelatedField(queryset=Rol.objects.all())
    correo = serializers.EmailField(max_length=100)
    password = serializers.CharField(write_only=True, required=False, min_length=6)

    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'telefono', 'correo', 'password', 'id_rol']

    def validate_telefono(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("El teléfono debe contener solo dígitos.")
        if len(value) > 10:
            raise serializers.ValidationError("El teléfono no puede exceder 10 dígitos.")
        return value

    def validate_correo(self, value):
        correo = value.lower()
        queryset = Usuario.objects.filter(correo__iexact=correo)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return correo

    def update(self, instance, validated_data):
        if 'password' in validated_data:
            validated_data['password'] = make_password(validated_data['password'])
        return super().update(instance, validated_data)


# ─────────────────────────────────────────────────────────────────────────────
# CU5 — Gestionar Barberos
# (Barbero = Usuario con rol "Barbero")
# ─────────────────────────────────────────────────────────────────────────────

class BarberoCrearSerializer(serializers.ModelSerializer):
    correo = serializers.EmailField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = Usuario
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'password']

    def validate_codigo(self, value):
        if not value.strip():
            raise serializers.ValidationError("El código no puede estar vacío.")
        return value.strip()

    def validate_telefono(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("El teléfono debe contener solo dígitos.")
        if len(value) > 10:
            raise serializers.ValidationError("El teléfono no puede exceder 10 dígitos.")
        return value

    def validate_correo(self, value):
        correo = value.lower()
        if Usuario.objects.filter(correo__iexact=correo).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return correo

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


class BarberoSerializer(serializers.ModelSerializer):
    """Serializer de solo lectura con datos del rol incluidos."""
    rol = serializers.CharField(source='id_rol.nombre', read_only=True)

    class Meta:
        model = Usuario
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'rol']
