# app_escuela/api/serializers.py
from rest_framework import serializers # type: ignore
from ..models import Matricula, Recibo, Usuario

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
    # horario_de_clases = seri... viene de asistencia/ cada asistencia 2 horas tanto practica
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
