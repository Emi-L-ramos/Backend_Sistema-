# app_escuela/api/serializers.py
from rest_framework import serializers # type: ignore
from ..models import Calendario, Matricula, Recibo, Usuario
from ..models import Instructor

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'rol', 'password']
        extra_kwargs = {'password': {'write_only': True, 'required': False}}

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = Usuario(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class MatriculaSerializer(serializers.ModelSerializer):
    horas_clases = serializers.SerializerMethodField()

    def get_horas_clases(self, obj):
        if 'reforz' in str(obj.tipo_curso).lower():
            return int(obj.horas_reforzamiento) if obj.horas_reforzamiento else 16
        return 16

    class Meta:
        model = Matricula
        fields = '__all__'
    

class ReciboSerializer(serializers.ModelSerializer):
    matricula_data = MatriculaSerializer(source='matricula', read_only=True)
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.SerializerMethodField()
    
    class Meta:
        model = Recibo
        fields = '__all__'
    
    def get_estudiante_nombre(self, obj):
        return f"{obj.matricula.nombre} {obj.matricula.apellido}"
    
    def get_estudiante_cedula(self, obj):
        return obj.matricula.cedula
    
class ReporteExcelSerializer(serializers.ModelSerializer):
    nombre = serializers.ReadOnlyField(source='nombre')
    apellido = serializers.ReadOnlyField(source='apellido')
    nacionalidad = serializers.ReadOnlyField(source='nacionalidad')
    n_documento = serializers.ReadOnlyField(source='cedula')
    telefonia = serializers.ReadOnlyField(source='telefono_movil')
    nivel_escolar = serializers.ReadOnlyField(source='nivel_educativo')
    tipo_de_curso = serializers.ReadOnlyField(source='tipo_curso')
    tipo_categoria = serializers.ReadOnlyField(source='categoria')
    fecha_inicio = serializers.ReadOnlyField(source='f_matricula')
    fecha_finalizacion = serializers.ReadOnlyField(source='Calendario.fecha_fin')
    # horario_de_clases = seri... viene de asistencia/ cada asistencia 2 horas practica
    calificacion_p = serializers.ReadOnlyField(source='Notas.examen_practico')
    calificacion_t = serializers.ReadOnlyField(source='Notas.examen_teorico')

    class Meta:
        model = Matricula
        fields = [
            'nombre', 'apellido', 'nacionalidad', 'n_documento', 
            'telefonia', 'nivel_escolar', 'tipo_de_curso', 
            'tipo_categoria', 'fecha_inicio', 'fecha_finalizacion', 
            'calificacion_p', 'calificacion_t'
        ]

class CalendarioSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.SerializerMethodField()
    instructor_nombre = serializers.SerializerMethodField()
    horario = serializers.SerializerMethodField()

    class Meta:
        model = Calendario
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        if obj.matricula:
            return f"{obj.matricula.nombre} {obj.matricula.apellido}"
        return ""

    def get_estudiante_cedula(self, obj):
        return obj.matricula.cedula if obj.matricula else ""

    def get_instructor_nombre(self, obj):
        if obj.instructor and obj.instructor.usuario:
            u = obj.instructor.usuario
            nombre = f"{u.first_name} {u.last_name}".strip()
            return nombre or u.username
        return ""

    def get_horario(self, obj):
        return obj.matricula.horario if obj.matricula else ""
  
# app_escuela/api/serializers.py

class CrearBloqueCitasSerializer(serializers.Serializer):
    instructor_id = serializers.IntegerField()
    matricula_id = serializers.IntegerField()
    fecha_inicio = serializers.DateField()
    horas_por_dia = serializers.IntegerField(default=2, required=False)

    def validate_fecha_inicio(self, value):
        # La regla depende de la modalidad de la matrícula, se valida en validate()
        return value

    def validate(self, data):
        from datetime import date

        try:
            matricula = Matricula.objects.get(pk=data['matricula_id'])
        except Matricula.DoesNotExist:
            raise serializers.ValidationError("Matrícula no encontrada.")

        es_extraordinario = (str(matricula.modalidad).lower() == 'extraordinario')
        es_finde = data['fecha_inicio'].weekday() >= 5

        if es_extraordinario and not es_finde:
            raise serializers.ValidationError(
                "Curso extraordinario: la fecha de inicio debe ser sábado o domingo."
            )
        if not es_extraordinario and es_finde:
            raise serializers.ValidationError(
                "Curso regular: la fecha de inicio no puede ser sábado o domingo."
            )

        es_reforzamiento = 'reforz' in str(matricula.tipo_curso).lower()

        horas_por_dia = data.get('horas_por_dia', 2)
        if es_reforzamiento:
            horas = int(matricula.horas_reforzamiento) if matricula.horas_reforzamiento else 16
            num_clases = horas // horas_por_dia
        else:
            num_clases = 16 // horas_por_dia

        existe_bloque_activo = Calendario.objects.filter(
            matricula_id=data['matricula_id'],
            fecha__gte=date.today(),
            numero_clase__lte=num_clases,
        ).exists()
        if existe_bloque_activo:
            raise serializers.ValidationError(
                "Esta matrícula ya tiene un bloque de clases en curso."
            )
        return data
        
class InstructorSerializer(serializers.ModelSerializer):
        nombre = serializers.SerializerMethodField()
        username = serializers.CharField(source='usuario.username', read_only=True)
        class Meta:
            model = Instructor
            fields = ['id', 'nombre', 'username', 'especialidad']
        def get_nombre(self, obj):
            if obj.usuario:
                n = f"{obj.usuario.first_name} {obj.usuario.last_name}".strip()
                return n or obj.usuario.username
            return "Sin nombre"
