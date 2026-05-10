from rest_framework import serializers
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from datetime import timedelta
from .models import AsistenciaBarbero, Bitacora, BloqueoHorario, HorarioLaboral, Rol, Usuario


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

        ahora = timezone.now()
        if usuario.bloqueado_hasta:
            if usuario.bloqueado_hasta > ahora:
                segundos = int((usuario.bloqueado_hasta - ahora).total_seconds())
                minutos = max(1, (segundos + 59) // 60)
                raise serializers.ValidationError({
                    "bloqueado": f"Usuario bloqueado temporalmente. Intente nuevamente en {minutos} minuto(s)."
                })

            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = None
            usuario.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])

        if not check_password(password, usuario.password):
            usuario.intentos_fallidos += 1

            if usuario.intentos_fallidos >= 3:
                usuario.bloqueado_hasta = ahora + timedelta(minutes=5)
                usuario.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
                raise serializers.ValidationError({
                    "bloqueado": "Usuario bloqueado por 3 intentos fallidos. Intente nuevamente en 5 minutos."
                })

            usuario.save(update_fields=['intentos_fallidos'])
            intentos_restantes = 3 - usuario.intentos_fallidos
            raise serializers.ValidationError({
                "password": f"Credenciales incorrectas. Intentos restantes: {intentos_restantes}."
            })

        if usuario.intentos_fallidos or usuario.bloqueado_hasta:
            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = None
            usuario.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])

        data['usuario'] = usuario
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class SolicitarRecuperacionSerializer(serializers.Serializer):
    correo = serializers.EmailField(max_length=100)


class ValidarCodigoRecuperacionSerializer(serializers.Serializer):
    correo = serializers.EmailField(max_length=100)
    codigo = serializers.CharField(min_length=6, max_length=6)


class RestablecerPasswordSerializer(serializers.Serializer):
    correo = serializers.EmailField(max_length=100)
    codigo = serializers.CharField(min_length=6, max_length=6)
    nueva_password = serializers.CharField(write_only=True, min_length=6)
    confirmar_password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, data):
        if data['nueva_password'] != data['confirmar_password']:
            raise serializers.ValidationError({"confirmar_password": "Las contraseñas no coinciden."})
        return data


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
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'especialidad', 'id_rol', 'rol']


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
    especialidad = serializers.CharField(max_length=100, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, min_length=6)

    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'telefono', 'correo', 'especialidad', 'password', 'id_rol']

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
    especialidad = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = Usuario
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'especialidad', 'password']

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

    def validate_especialidad(self, value):
        if not value.strip():
            raise serializers.ValidationError("La especialidad no puede estar vacía.")
        return value.strip()

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


class ClienteRegistroSerializer(serializers.ModelSerializer):
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
        fields = ['codigo', 'nombre', 'apellido', 'telefono', 'correo', 'especialidad', 'rol']


class BitacoraSerializer(serializers.ModelSerializer):
    usuario = serializers.SerializerMethodField()
    usuario_codigo = serializers.CharField(source='usuario.codigo', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    usuario_rol = serializers.CharField(source='usuario.id_rol.nombre', read_only=True)

    class Meta:
        model = Bitacora
        fields = [
            'id',
            'fecha',
            'usuario',
            'usuario_codigo',
            'usuario_nombre',
            'usuario_rol',
            'accion',
            'descripcion',
            'metodo',
            'ruta',
            'ip',
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_usuario(self, obj):
        if not obj.usuario:
            return None
        nombre = f"{obj.usuario.nombre} {obj.usuario.apellido}".strip()
        return f"{nombre} ({obj.usuario.codigo})" if nombre else obj.usuario.codigo

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return f"{obj.usuario.nombre} {obj.usuario.apellido}".strip()


class HorarioLaboralSerializer(serializers.ModelSerializer):
    codigo_barbero = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='barbero')
    )
    barbero = serializers.SerializerMethodField(read_only=True)
    dia_semana = serializers.CharField(max_length=15)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = HorarioLaboral
        fields = [
            'id_horario',
            'codigo_barbero',
            'barbero',
            'dia_semana',
            'hora_inicio',
            'hora_fin',
            'hora_inicio_descanso',
            'hora_fin_descanso',
            'estado',
            'observacion',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    def validate_dia_semana(self, value):
        dia = value.upper()
        dias_validos = dict(HorarioLaboral.DIAS_SEMANA)
        if dia not in dias_validos:
            raise serializers.ValidationError("Dia de la semana invalido.")
        return dia

    def validate_estado(self, value):
        estado = value.upper()
        estados_validos = dict(HorarioLaboral.ESTADOS)
        if estado not in estados_validos:
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        barbero = data.get('codigo_barbero', getattr(instance, 'codigo_barbero', None))
        dia_semana = data.get('dia_semana', getattr(instance, 'dia_semana', None))
        hora_inicio = data.get('hora_inicio', getattr(instance, 'hora_inicio', None))
        hora_fin = data.get('hora_fin', getattr(instance, 'hora_fin', None))
        hora_inicio_descanso = data.get('hora_inicio_descanso', getattr(instance, 'hora_inicio_descanso', None))
        hora_fin_descanso = data.get('hora_fin_descanso', getattr(instance, 'hora_fin_descanso', None))
        estado = data.get('estado', getattr(instance, 'estado', 'ACTIVO'))

        if not barbero or not barbero.es_barbero:
            raise serializers.ValidationError({"codigo_barbero": "El usuario seleccionado debe tener rol Barbero."})

        if hora_inicio >= hora_fin:
            raise serializers.ValidationError({"hora_fin": "La hora fin debe ser mayor que la hora inicio."})

        descanso_incompleto = (hora_inicio_descanso and not hora_fin_descanso) or (hora_fin_descanso and not hora_inicio_descanso)
        if descanso_incompleto:
            raise serializers.ValidationError("Debe enviar hora inicio y hora fin del descanso.")

        if hora_inicio_descanso and hora_fin_descanso:
            if not (hora_inicio < hora_inicio_descanso < hora_fin_descanso < hora_fin):
                raise serializers.ValidationError("El descanso debe estar dentro del horario laboral.")

        if estado == 'ACTIVO':
            horarios_cruzados = HorarioLaboral.objects.filter(
                codigo_barbero=barbero,
                dia_semana=dia_semana,
                estado='ACTIVO',
                hora_inicio__lt=hora_fin,
                hora_fin__gt=hora_inicio,
            )
            if instance:
                horarios_cruzados = horarios_cruzados.exclude(pk=instance.pk)
            if horarios_cruzados.exists():
                raise serializers.ValidationError("Ya existe un horario activo cruzado para este barbero en ese día.")

        return data


class BloqueoHorarioSerializer(serializers.ModelSerializer):
    codigo_barbero = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='barbero')
    )
    barbero = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20, required=False)

    class Meta:
        model = BloqueoHorario
        fields = [
            'id_bloqueo',
            'codigo_barbero',
            'barbero',
            'fecha',
            'hora_inicio',
            'hora_fin',
            'motivo',
            'estado',
            'fecha_registro',
        ]
        read_only_fields = ['fecha_registro']

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    def validate_estado(self, value):
        estado = value.upper()
        estados_validos = dict(BloqueoHorario.ESTADOS)
        if estado not in estados_validos:
            raise serializers.ValidationError("Estado invalido.")
        return estado

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        barbero = data.get('codigo_barbero', getattr(instance, 'codigo_barbero', None))
        fecha = data.get('fecha', getattr(instance, 'fecha', None))
        hora_inicio = data.get('hora_inicio', getattr(instance, 'hora_inicio', None))
        hora_fin = data.get('hora_fin', getattr(instance, 'hora_fin', None))
        estado = data.get('estado', getattr(instance, 'estado', 'ACTIVO'))

        if not barbero or not barbero.es_barbero:
            raise serializers.ValidationError({"codigo_barbero": "El usuario seleccionado debe tener rol Barbero."})

        if hora_inicio >= hora_fin:
            raise serializers.ValidationError({"hora_fin": "La hora fin debe ser mayor que la hora inicio."})

        if estado == 'ACTIVO':
            bloqueos_cruzados = BloqueoHorario.objects.filter(
                codigo_barbero=barbero,
                fecha=fecha,
                estado='ACTIVO',
                hora_inicio__lt=hora_fin,
                hora_fin__gt=hora_inicio,
            )
            if instance:
                bloqueos_cruzados = bloqueos_cruzados.exclude(pk=instance.pk)
            if bloqueos_cruzados.exists():
                raise serializers.ValidationError("Ya existe un bloqueo activo cruzado para este barbero en esa fecha.")

        return data


class AsistenciaBarberoSerializer(serializers.ModelSerializer):
    codigo_barbero = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.select_related('id_rol').filter(id_rol__nombre__iexact='barbero')
    )
    barbero = serializers.SerializerMethodField(read_only=True)
    estado = serializers.CharField(max_length=20)

    class Meta:
        model = AsistenciaBarbero
        fields = [
            'id_asistencia',
            'codigo_barbero',
            'barbero',
            'fecha',
            'estado',
            'hora_entrada',
            'hora_salida',
            'observacion',
            'fecha_registro',
            'fecha_actualizacion',
        ]
        read_only_fields = ['fecha_registro', 'fecha_actualizacion']

    @extend_schema_field(serializers.CharField())
    def get_barbero(self, obj):
        return f"{obj.codigo_barbero.nombre} {obj.codigo_barbero.apellido}".strip()

    def validate_estado(self, value):
        estado = value.upper()
        estados_validos = dict(AsistenciaBarbero.ESTADOS)
        if estado not in estados_validos:
            raise serializers.ValidationError("Estado de asistencia invalido.")
        return estado

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        barbero = data.get('codigo_barbero', getattr(instance, 'codigo_barbero', None))
        fecha = data.get('fecha', getattr(instance, 'fecha', None))
        estado = data.get('estado', getattr(instance, 'estado', None))
        hora_entrada = data.get('hora_entrada', getattr(instance, 'hora_entrada', None))
        hora_salida = data.get('hora_salida', getattr(instance, 'hora_salida', None))

        if not barbero or not barbero.es_barbero:
            raise serializers.ValidationError({"codigo_barbero": "El usuario seleccionado debe tener rol Barbero."})

        if estado in ['PRESENTE', 'TARDE'] and not hora_entrada:
            raise serializers.ValidationError({"hora_entrada": "La hora de entrada es obligatoria para Presente o Tarde."})

        if hora_salida and not hora_entrada:
            raise serializers.ValidationError({"hora_entrada": "Debe registrar hora de entrada antes de hora de salida."})

        if hora_entrada and hora_salida and hora_salida <= hora_entrada:
            raise serializers.ValidationError({"hora_salida": "La hora de salida debe ser mayor que la hora de entrada."})

        asistencia_existente = AsistenciaBarbero.objects.filter(
            codigo_barbero=barbero,
            fecha=fecha,
        )
        if instance:
            asistencia_existente = asistencia_existente.exclude(pk=instance.pk)
        if asistencia_existente.exists():
            raise serializers.ValidationError("Ya existe asistencia registrada para este barbero en esa fecha.")

        return data
