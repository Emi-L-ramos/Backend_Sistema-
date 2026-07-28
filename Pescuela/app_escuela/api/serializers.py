# app_escuela/api/serializers.py

import base64
import binascii
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from PIL import Image as PILImage, UnidentifiedImageError
from rest_framework import serializers
from django.db import models
from django.utils import timezone
from django.contrib.auth.password_validation import (
    validate_password as django_validate_password,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from ..models import (
    Rol,
    Usuario,
    Estudiante,
    Instructor,
    CategoriaVehiculo,
    PlanEstudio,
    Matricula,
    Recibo,
    Calendario,
    Asistencia,
    Notas,
    ValorCurso,
    TemaPlanEstudio,
    SubtemaPlanEstudio,
    PreguntaExamenTeorico,
    OpcionPreguntaExamenTeorico,
    ExamenTeorico,
    RespuestaExamenTeorico,
    PagoInstructor,
    CargoInstitucional,
)
from django.db import transaction
from ..models import ProgresoTema, ProgresoClaseTema, HistorialPlanEstudio, Notificacion
from ..models import PlanEstudio, SubtemaPlanEstudio

def actualizar_estado_matricula_por_notas(matricula):
    """
    Finaliza la matrícula cuando existe una nota práctica
    y la nota teórica es igual o mayor a 80.
    """

    if matricula is None or not matricula.pk:
        return False

    with transaction.atomic():
        matricula_bloqueada = (
            Matricula.objects
            .select_for_update()
            .get(
                pk=matricula.pk
            )
        )

        tiene_nota_practica = (
            Notas.objects
            .filter(
                matricula_id=matricula_bloqueada.id,
                tipo_nota='practico',
            )
            .exists()
        )

        nota_teorica = (
            Notas.objects
            .filter(
                matricula_id=matricula_bloqueada.id,
                tipo_nota='teorico',
            )
            .order_by(
                '-fecha_registro',
                '-id',
            )
            .first()
        )

        if not tiene_nota_practica or not nota_teorica:
            return False

        try:
            valor_nota_teorica = Decimal(
                str(nota_teorica.nota)
                .strip()
                .replace(',', '.')
            )
        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            return False

        if valor_nota_teorica < Decimal('80'):
            return False

        campos_actualizados = []

        if matricula_bloqueada.estado != 'finalizado':
            matricula_bloqueada.estado = 'finalizado'
            campos_actualizados.append(
                'estado'
            )

        if not matricula_bloqueada.fecha_finalizacion:
            matricula_bloqueada.fecha_finalizacion = (
                timezone.now()
            )

            campos_actualizados.append(
                'fecha_finalizacion'
            )

        if campos_actualizados:
            matricula_bloqueada.save(
                update_fields=campos_actualizados
            )

        matricula.estado = matricula_bloqueada.estado

        matricula.fecha_finalizacion = (
            matricula_bloqueada.fecha_finalizacion
        )

        return True

class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    rol = serializers.SlugRelatedField(
        queryset=Rol.objects.all(),
        slug_field='nombre',
        allow_null=True,
        required=False,
    )

    matricula_id = serializers.IntegerField(write_only=True, required=False)
    instructor_id = serializers.IntegerField(write_only=True, required=False)
    estudiante_nombre = serializers.SerializerMethodField()
    instructor_nombre = serializers.SerializerMethodField()
    texto_estado_usuario = serializers.SerializerMethodField()
    tiene_matricula_activa = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'rol',
            'password',
            'is_active',
            'matricula_id',
            'instructor_id',
            'estudiante_nombre',
            'instructor_nombre',
            'texto_estado_usuario',
            'tiene_matricula_activa',
        ]
        extra_kwargs = {
            'password': {
                'write_only': True,
                'required': False,
            }
        }

    def validate_password(self, password):
        usuario = self.instance if self.instance else None

        try:
            django_validate_password(
                password,
                user=usuario,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                list(error.messages)
            )

        return password

    def get_estudiante_nombre(self, obj):
        if obj.estudiante:
            return f"{obj.estudiante.nombre or ''} {obj.estudiante.apellido or ''}".strip()
        return None

    def get_instructor_nombre(self, obj):
        if obj.instructor:
            return f"{obj.instructor.nombre or ''} {obj.instructor.apellido or ''}".strip()
        return None

    def obtener_matriculas_usuario(self, obj):
        if not obj.estudiante:
            return []

        matriculas_precargadas = getattr(
            obj.estudiante,
            'matriculas_usuario_precargadas',
            None,
        )

        if matriculas_precargadas is not None:
            return matriculas_precargadas

        return list(
            obj.estudiante.matriculas
            .only(
                'id',
                'estudiante_id',
                'estado',
            )
            .order_by('-id')
        )

    def obtener_matricula_actual_usuario(self, obj):
        matriculas = self.obtener_matriculas_usuario(obj)

        return matriculas[0] if matriculas else None

    def get_tiene_matricula_activa(self, obj):
        if not obj.estudiante:
            return None

        return any(
            matricula.estado != 'finalizado'
            for matricula in self.obtener_matriculas_usuario(obj)
        )

    def get_texto_estado_usuario(self, obj):
        rol_nombre = str(
            obj.rol.nombre if obj.rol else ''
        ).strip().lower()

        if rol_nombre != 'estudiante':
            return 'Activo' if obj.is_active else 'Inactivo'

        matricula_activa = next(
            (
                matricula
                for matricula in self.obtener_matriculas_usuario(obj)
                if matricula.estado != 'finalizado'
            ),
            None,
        )

        if matricula_activa:
            estado = str(
                matricula_activa.estado or ''
            ).strip().lower()

            if estado == 'matriculado':
                return 'Activo'

            if estado == 'pendiente':
                return 'Pendiente'

            return estado.capitalize()

        matricula_actual = self.obtener_matricula_actual_usuario(
            obj
        )

        if matricula_actual and matricula_actual.estado == 'finalizado':
            return 'Finalizado'

        return 'Inactivo'

    def validate(self, data):
        matricula_id = data.get('matricula_id')
        instructor_id = data.get('instructor_id')

        rol = data.get('rol') or getattr(self.instance, 'rol', None)
        rol_nombre = rol.nombre.lower() if rol else ""

        if rol_nombre == "estudiante":
            if not matricula_id and not self.instance:
                raise serializers.ValidationError({
                    'matricula_id': 'Debe seleccionar una matrícula para crear un usuario estudiante.'
                })

            if matricula_id:
                try:
                    matricula = Matricula.objects.select_related('estudiante').get(id=matricula_id)
                except Matricula.DoesNotExist:
                    raise serializers.ValidationError({
                        'matricula_id': 'La matrícula no existe.'
                    })

                if matricula.estado == 'finalizado':
                    raise serializers.ValidationError({
                        'matricula_id': (
                            'No se puede crear usuario para una '
                            'matrícula finalizada.'
                        )
                    })

                if Usuario.objects.filter(
                    estudiante=matricula.estudiante,
                    rol__nombre__iexact='estudiante'
                ).exclude(id=getattr(self.instance, 'id', None)).exists():
                    raise serializers.ValidationError({
                        'matricula_id': 'Este estudiante ya tiene un usuario asignado.'
                    })

        if rol_nombre == "instructor":
            if not instructor_id and not self.instance:
                raise serializers.ValidationError({
                    'instructor_id': 'Debe seleccionar un instructor para crear un usuario instructor.'
                })

            if instructor_id:
                try:
                    instructor = Instructor.objects.get(id=instructor_id)
                except Instructor.DoesNotExist:
                    raise serializers.ValidationError({
                        'instructor_id': 'El instructor no existe.'
                    })

                if Usuario.objects.filter(
                    instructor=instructor,
                    rol__nombre__iexact='instructor'
                ).exclude(id=getattr(self.instance, 'id', None)).exists():
                    raise serializers.ValidationError({
                        'instructor_id': 'Este instructor ya tiene un usuario asignado.'
                    })

        return data

    def create(self, validated_data):
        matricula_id = validated_data.pop('matricula_id', None)
        instructor_id = validated_data.pop('instructor_id', None)
        password = validated_data.pop('password', None)

        usuario = Usuario(**validated_data)

        if password:
            usuario.set_password(password)
        else:
            usuario.set_unusable_password()

        usuario.save()

        if matricula_id:
            matricula = Matricula.objects.select_related('estudiante').get(id=matricula_id)
            usuario.estudiante = matricula.estudiante
            usuario.save(update_fields=['estudiante'])

        rol_nombre = usuario.rol.nombre.lower() if usuario.rol else ""

        if rol_nombre == "instructor" and instructor_id:
            instructor = Instructor.objects.get(id=instructor_id)
            usuario.instructor = instructor
            usuario.save(update_fields=['instructor'])

        return usuario

    def update(self, instance, validated_data):
        validated_data.pop('matricula_id', None)
        validated_data.pop('instructor_id', None)
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance

class SubtemaPlanEstudioSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = SubtemaPlanEstudio
        fields = ['id', 'titulo', 'orden', 'activo']


class TemaPlanEstudioSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    subtemas = SubtemaPlanEstudioSerializer(many=True, required=False)

    class Meta:
        model = TemaPlanEstudio
        fields = ['id', 'titulo', 'orden', 'activo', 'subtemas']

    def to_representation(self, instance):
        data = super().to_representation(instance)

        subtemas_activos = sorted(
            (
                subtema
                for subtema in instance.subtemas.all()
                if subtema.activo
            ),
            key=lambda subtema: (
                subtema.orden or 0,
                subtema.id,
            )
        )

        data['subtemas'] = (
            SubtemaPlanEstudioSerializer(
                subtemas_activos,
                many=True
            ).data
        )

        return data

class PlanEstudioSerializer(serializers.ModelSerializer):
    temas = TemaPlanEstudioSerializer(many=True, required=False)

    class Meta:
        model = PlanEstudio
        fields = [
            'id',
            'nombre',
            'tipo_curso',
            'activo',
            'temas',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        temas_activos = sorted(
            (
                tema
                for tema in instance.temas.all()
                if tema.activo
            ),
            key=lambda tema: (
                tema.orden or 0,
                tema.id,
            )
        )

        data['temas'] = TemaPlanEstudioSerializer(
            temas_activos,
            many=True
        ).data

        return data

    def limpiar_texto(self, valor):
        return str(valor or '').strip()

    def limpiar_id(self, valor):
        if valor in [None, '', 'null', 'undefined']:
            return None

        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    def limpiar_orden(self, valor, defecto):
        if valor in [None, '', 'null', 'undefined']:
            return defecto

        try:
            numero = int(valor)

            if numero <= 0:
                return defecto

            return numero
        except (TypeError, ValueError):
            return defecto


    def normalizar_lista(self, valor):
        if isinstance(valor, list):
            return valor

        return []

    def obtener_o_crear_tema(self, plan, tema_data, index_tema):
        tema_id = self.limpiar_id(tema_data.get('id'))
        titulo_tema = self.limpiar_texto(tema_data.get('titulo'))
        orden_tema = self.limpiar_orden(
            tema_data.get('orden'),
            index_tema
        )

        if not titulo_tema:
            return None

        tema = None

        if tema_id:
            tema = TemaPlanEstudio.objects.filter(
                id=tema_id,
                plan_estudio=plan
            ).first()

        if not tema:
            tema = TemaPlanEstudio.objects.filter(
                plan_estudio=plan,
                titulo__iexact=titulo_tema
            ).order_by(
                '-activo',
                'id'
            ).first()

        if tema:
            tema.titulo = titulo_tema
            tema.orden = orden_tema
            tema.activo = True
            tema.save()
            return tema

        return TemaPlanEstudio.objects.create(
            plan_estudio=plan,
            titulo=titulo_tema,
            orden=orden_tema,
            activo=True,
        )

    def obtener_o_crear_subtema(self, tema, subtema_data, index_subtema):
        subtema_id = self.limpiar_id(subtema_data.get('id'))
        titulo_subtema = self.limpiar_texto(subtema_data.get('titulo'))
        orden_subtema = self.limpiar_orden(
            subtema_data.get('orden'),
            index_subtema
        )

        if not titulo_subtema:
            return None

        subtema = None

        if subtema_id:
            subtema = SubtemaPlanEstudio.objects.filter(
                id=subtema_id,
                tema=tema
            ).first()

        if not subtema:
            subtema = SubtemaPlanEstudio.objects.filter(
                tema=tema,
                titulo__iexact=titulo_subtema
            ).order_by(
                '-activo',
                'id'
            ).first()

        if subtema:
            subtema.titulo = titulo_subtema
            subtema.orden = orden_subtema
            subtema.activo = True
            subtema.save()
            return subtema

        return SubtemaPlanEstudio.objects.create(
            tema=tema,
            titulo=titulo_subtema,
            orden=orden_subtema,
            activo=True,
        )

    def guardar_subtemas(self, tema, subtemas_data):
        subtemas_data = self.normalizar_lista(subtemas_data)

        ids_subtemas_recibidos = []

        for index_subtema, subtema_data in enumerate(subtemas_data, start=1):
            if not isinstance(subtema_data, dict):
                continue
            subtema = self.obtener_o_crear_subtema(
                tema,
                subtema_data,
                index_subtema
            )

            if subtema:
                ids_subtemas_recibidos.append(subtema.id)

        tema.subtemas.exclude(
            id__in=ids_subtemas_recibidos
        ).update(
            activo=False
        )

    @transaction.atomic
    def create(self, validated_data):
        temas_data = validated_data.pop('temas', [])
        temas_data = self.normalizar_lista(temas_data)

        plan = PlanEstudio.objects.create(**validated_data)

        for index_tema, tema_data in enumerate(temas_data, start=1):
            if not isinstance(tema_data, dict):
                continue
            subtemas_data = tema_data.pop('subtemas', [])

            tema = self.obtener_o_crear_tema(
                plan,
                tema_data,
                index_tema
            )

            if tema:
                self.guardar_subtemas(
                    tema,
                    subtemas_data
                )

        return plan

    @transaction.atomic
    def update(self, instance, validated_data):
        temas_data = validated_data.pop('temas', None)

        instance.nombre = validated_data.get('nombre', instance.nombre)
        instance.tipo_curso = validated_data.get('tipo_curso', instance.tipo_curso)
        instance.activo = validated_data.get('activo', instance.activo)
        instance.save()

        if temas_data is None:
            return instance

        temas_data = self.normalizar_lista(temas_data)

        tipo_curso_final = validated_data.get(
            'tipo_curso',
            instance.tipo_curso
        )

        ids_temas_recibidos = []

        for index_tema, tema_data in enumerate(temas_data, start=1):
            if not isinstance(tema_data, dict):
                continue
            subtemas_data = tema_data.pop('subtemas', [])

            tema = self.obtener_o_crear_tema(
                instance,
                tema_data,
                index_tema
            )

            if not tema:
                continue

            ids_temas_recibidos.append(tema.id)

            self.guardar_subtemas(
                tema,
                subtemas_data
            )

        instance.temas.exclude(
            id__in=ids_temas_recibidos
        ).update(
            activo=False
        )

        return instance



class ValorCursoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorCurso
        fields = '__all__'

class CategoriaVehiculoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaVehiculo
        fields = '__all__'

class EstudianteSerializer(serializers.ModelSerializer):
    usuario_data = serializers.SerializerMethodField()
    tiene_matricula_activa = serializers.SerializerMethodField()
    estado_matricula_actual = serializers.SerializerMethodField()
    texto_estado_academico = serializers.SerializerMethodField()

    class Meta:
        model = Estudiante
        fields = '__all__'
        read_only_fields = ['codigo_estudiante']

    def get_usuario_data(self, obj):
        usuarios_precargados = getattr(
            obj,
            'usuarios_estudiante_precargados',
            None,
        )

        if usuarios_precargados is not None:
            usuario = (
                usuarios_precargados[0]
                if usuarios_precargados
                else None
            )
        else:
            usuario = (
                obj.usuarios
                .filter(
                    rol__nombre__iexact='estudiante'
                )
                .select_related('rol')
                .order_by('id')
                .first()
            )

        if not usuario:
            return None

        return {
            'id': usuario.id,
            'username': usuario.username,
            'email': usuario.email,
            'first_name': usuario.first_name,
            'last_name': usuario.last_name,
            'rol': usuario.rol.nombre if usuario.rol else None,
        }

    def obtener_matriculas(self, obj):
        matriculas_precargadas = getattr(
            obj,
            'matriculas_precargadas',
            None,
        )

        if matriculas_precargadas is not None:
            return matriculas_precargadas

        return list(
            obj.matriculas
            .only(
                'id',
                'estudiante_id',
                'estado',
            )
            .order_by('-id')
        )

    def obtener_matricula_actual(self, obj):
        matriculas = self.obtener_matriculas(obj)

        return matriculas[0] if matriculas else None

    def get_tiene_matricula_activa(self, obj):
        return any(
            matricula.estado != 'finalizado'
            for matricula in self.obtener_matriculas(obj)
        )

    def get_estado_matricula_actual(self, obj):
        matricula = self.obtener_matricula_actual(obj)

        if not matricula:
            return None

        return matricula.estado

    def get_texto_estado_academico(self, obj):
        matricula_activa = next(
            (
                matricula
                for matricula in self.obtener_matriculas(obj)
                if matricula.estado != 'finalizado'
            ),
            None,
        )

        if matricula_activa:
            estado = str(
                matricula_activa.estado or ''
            ).strip().lower()

            if estado == 'pendiente':
                return 'Pendiente'

            if estado == 'matriculado':
                return 'Activo'

            return estado.capitalize()

        matricula_actual = self.obtener_matricula_actual(obj)

        if (
            matricula_actual
            and matricula_actual.estado == 'finalizado'
        ):
            return 'Finalizado'

        return 'Sin matrícula'

class InstructorSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()
    categoria_nombre = serializers.SerializerMethodField()

    foto_base64 = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        write_only=True,
    )

    tiene_foto = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = '__all__'

    def get_nombre_completo(self, obj):
        nombre = f"{obj.nombre or ''} {obj.apellido or ''}".strip()
        return nombre or f"Instructor {obj.id}"

    def get_categoria_nombre(self, obj):
        return obj.categoria_instructor or ""

    def get_tiene_foto(self, obj):
        return bool(obj.foto_base64)

    def validate_foto_base64(self, valor):
        if valor in (None, ""):
            return valor

        if not isinstance(valor, str) or ',' not in valor:
            raise serializers.ValidationError(
                'La fotografía no tiene un formato válido.'
            )

        encabezado, contenido_codificado = valor.split(',', 1)

        formatos_permitidos = {
            'data:image/jpeg;base64': 'JPEG',
            'data:image/png;base64': 'PNG',
            'data:image/webp;base64': 'WEBP',
        }

        formato_esperado = formatos_permitidos.get(
            encabezado.lower()
        )

        if not formato_esperado:
            raise serializers.ValidationError(
                'La fotografía debe ser JPG, PNG o WEBP.'
            )

        if len(contenido_codificado) > 2_800_000:
            raise serializers.ValidationError(
                'La fotografía es demasiado grande.'
            )

        try:
            contenido = base64.b64decode(
                contenido_codificado,
                validate=True,
            )
        except (binascii.Error, ValueError):
            raise serializers.ValidationError(
                'La fotografía contiene datos inválidos.'
            )

        if len(contenido) > 2 * 1024 * 1024:
            raise serializers.ValidationError(
                'La fotografía no puede superar 2 MB.'
            )

        try:
            imagen = PILImage.open(BytesIO(contenido))
            formato_real = (imagen.format or '').upper()
            ancho, alto = imagen.size
            imagen.verify()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            PILImage.DecompressionBombError,
        ):
            raise serializers.ValidationError(
                'El archivo enviado no es una imagen válida.'
            )

        if formato_real != formato_esperado:
            raise serializers.ValidationError(
                'El contenido de la fotografía no coincide con su formato.'
            )

        if ancho > 2000 or alto > 2000:
            raise serializers.ValidationError(
                'La fotografía no puede superar 2000 x 2000 píxeles.'
            )

        return valor

class InstructorListSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()
    categoria_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        exclude = ['foto_base64']

    def get_nombre_completo(self, obj):
        nombre = f"{obj.nombre or ''} {obj.apellido or ''}".strip()
        return nombre or f"Instructor {obj.id}"

    def get_categoria_nombre(self, obj):
        return obj.categoria_instructor or ""

class InstructorCalendarioSerializer(
    serializers.ModelSerializer
):
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = [
            'id',
            'nombre',
            'apellido',
            'nombre_completo',
            'activo',
        ]

    def get_nombre_completo(self, obj):
        nombre = (
            f"{obj.nombre or ''} {obj.apellido or ''}"
        ).strip()

        return nombre or f"Instructor {obj.id}"

class MatriculaSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(source='estudiante.cedula', read_only=True)
    estudiante_telefono = serializers.CharField(source='estudiante.telefono_movil', read_only=True)
    estudiante_correo = serializers.CharField(source='estudiante.correo_electronico', read_only=True)
    estudiante_edad = serializers.IntegerField(source='estudiante.edad', read_only=True)
    estudiante_sexo = serializers.CharField(source='estudiante.sexo', read_only=True)
    estudiante_nacionalidad = serializers.CharField(source='estudiante.nacionalidad', read_only=True)
    estudiante_fecha_nacimiento = serializers.DateField(source='estudiante.fecha_nacimiento', read_only=True)
    estudiante_direccion = serializers.CharField(source='estudiante.direccion', read_only=True)
    estudiante_nivel_educativo = serializers.CharField(source='estudiante.nivel_educativo', read_only=True)
    estudiante_contacto_emergencia = serializers.CharField(source='estudiante.nombre_emergencia', read_only=True)
    estudiante_telefono_emergencia = serializers.CharField(source='estudiante.telefono_emergencia', read_only=True)
    tiene_usuario = serializers.SerializerMethodField()
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    usa_checks = serializers.SerializerMethodField()

    class Meta:
        model = Matricula
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        return f"{obj.estudiante.nombre} {obj.estudiante.apellido}"

    def get_tiene_usuario(self, obj):
        usuarios_precargados = getattr(
            obj.estudiante,
            'usuarios_precargados',
            None,
        )

        if usuarios_precargados is not None:
            return bool(usuarios_precargados)

        return obj.estudiante.usuarios.exists()

    def get_usa_checks(self, obj):
        tipo_curso = str(
            getattr(obj, 'tipo_curso', '') or ''
        ).strip().lower()

        return tipo_curso == 'principiante'

#Cambios realizados es decir sse agreagron
    def validate(self, data):
        tipo_curso = data.get(
            'tipo_curso',
            getattr(self.instance, 'tipo_curso', None)
        )

        horas_reforzamiento = data.get(
            'horas_reforzamiento',
            getattr(self.instance, 'horas_reforzamiento', None)
        )

        incluye_examen_policial = data.get(
            'incluye_examen_policial',
            getattr(
                self.instance,
                'incluye_examen_policial',
                False
            )
        )

        # Principiante no utiliza esta nueva opción.
        if tipo_curso == 'Principiante':
            data['incluye_examen_policial'] = False
            return data

        # La nueva opción solo corresponde a Intermedio y Avanzado.
        if tipo_curso in ['Intermedio', 'Avanzado']:
            if not horas_reforzamiento:
                raise serializers.ValidationError({
                    'horas_reforzamiento': (
                        'Debe ingresar la cantidad de horas '
                        'de reforzamiento.'
                    )
                })

            if (
                incluye_examen_policial
                and int(horas_reforzamiento) < 3
            ):
                raise serializers.ValidationError({
                    'horas_reforzamiento': (
                        'Para incluir el examen policial debe '
                        'seleccionar al menos 3 horas: '
                        '1 hora práctica y 2 horas para el examen.'
                    )
                })

            return data

        # Protección para cualquier otro tipo de curso.
        data['incluye_examen_policial'] = False

        return data

    @transaction.atomic
    def create(self, validated_data):
        tipo_curso = validated_data.get(
            'tipo_curso'
        )

        estudiante = validated_data.get(
            'estudiante'
        )

        estudiante_bloqueado = (
            Estudiante.objects
            .select_for_update()
            .get(
                pk=estudiante.pk
            )
        )

        matricula_sin_finalizar = (
            Matricula.objects
            .filter(
                estudiante_id=estudiante_bloqueado.id
            )
            .exclude(
                estado='finalizado'
            )
            .order_by(
                '-id'
            )
            .first()
        )

        if matricula_sin_finalizar:
            raise serializers.ValidationError({
                'estudiante': (
                    'Este estudiante ya tiene la matrícula '
                    f'#{matricula_sin_finalizar.id} en estado '
                    f'{matricula_sin_finalizar.get_estado_display()}. '
                    'Debe finalizar esa matrícula antes de '
                    'crear una nueva.'
                )
            })

        validated_data[
            'estudiante'
        ] = estudiante_bloqueado

        plan_principal = (
            PlanEstudio.objects
            .filter(
                tipo_curso=tipo_curso,
                activo=True,
            )
            .order_by(
                '-id'
            )
            .first()
        )

        if not plan_principal:
            raise serializers.ValidationError({
                'plan_de_estudio': (
                    'No existe un plan de estudio activo '
                    f'para el curso {tipo_curso}.'
                )
            })

        validated_data['plan_de_estudio'] = plan_principal

        matricula = Matricula.objects.create(**validated_data)

        temas = TemaPlanEstudio.objects.filter(
            plan_estudio=plan_principal,
            activo=True,
        ).order_by(
            'orden',
            'id',
        )

        for orden_general, tema in enumerate(temas, start=1):
            ProgresoTema.objects.create(
                matricula=matricula,
                tema=tema,
                orden_general=orden_general,
                desbloqueado=(
                    str(tipo_curso).strip().lower()
                    in ['intermedio', 'avanzado']
                ),
                estudiante_completado=False,
                instructor_completado=False,
                completado=False,
            )

        if matricula.estudiante and not matricula.estudiante.activo:
            matricula.estudiante.activo = True
            matricula.estudiante.save(
                update_fields=[
                    'activo',
                ]
            )

        return matricula

class ReciboSerializer(serializers.ModelSerializer):
    matricula_data = MatriculaSerializer(
        source='matricula',
        read_only=True
    )

    estudiante_nombre = serializers.SerializerMethodField()

    estudiante_cedula = serializers.CharField(
        source='matricula.estudiante.cedula',
        read_only=True
    )

    monto_total_curso = serializers.SerializerMethodField()
    por_pagar = serializers.SerializerMethodField()

    class Meta:
        model = Recibo
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante

        return (
            f"{estudiante.nombre} "
            f"{estudiante.apellido}"
        ).strip()

    def get_monto_total_curso(self, obj):
        matricula = obj.matricula
        valor_curso = obj.valor_curso

        if not valor_curso:
            try:
                valor_curso = self.obtener_valor_curso(
                    matricula
                )
            except serializers.ValidationError:
                return Decimal('0.00')
 
        monto_total = Decimal(
            str(valor_curso.precio_total or 0)
        )

        return monto_total.quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )

    def get_por_pagar(self, obj):
        tipo_pago = str(
            obj.tipo_pago or ''
        ).strip().lower()

        # Solamente los anticipos tienen saldo pendiente.
        if tipo_pago != 'anticipo':
            return Decimal('0.00')

        monto_total = Decimal(
            str(self.get_monto_total_curso(obj))
        )

        monto_pagado = Decimal(
            str(obj.monto_pagado or 0)
        )

        return max(
            monto_total - monto_pagado,
            Decimal('0.00'),
        ).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )

    def obtener_valor_curso(self, matricula):
        """
        Si la matrícula ya tiene un recibo, se conserva
        el valor del curso utilizado en ese primer pago.

        Esto evita que un cambio posterior en el precio
        altere el saldo pendiente del estudiante.
        """

        primer_recibo = (
            Recibo.objects
            .filter(
                matricula=matricula,
                valor_curso__isnull=False,
            )
            .select_related('valor_curso')
            .order_by('id')
            .first()
        )

        if primer_recibo:
            return primer_recibo.valor_curso

        valor_curso = (
            ValorCurso.objects
            .filter(
                tipo_curso=matricula.tipo_curso,
                activo=True,
            )
            .order_by(
                '-fecha_modificacion',
                '-id',
            )
            .first()
        )

        if not valor_curso:
            raise serializers.ValidationError(
                f'No existe un valor activo para el curso '
                f'{matricula.tipo_curso}.'
            )

        return valor_curso

    def calcular_monto_total(self, matricula):
        valor_curso = self.obtener_valor_curso(
            matricula
        )

        if matricula.tipo_curso == 'Principiante':
            monto_total = Decimal(
                str(valor_curso.precio_total)
            )

        elif matricula.tipo_curso in [
            'Intermedio',
            'Avanzado',
        ]:
            horas = matricula.horas_reforzamiento

            if not horas:
                raise serializers.ValidationError(
                    f'El curso {matricula.tipo_curso} '
                    f'requiere horas.'
                )

            monto_total = (
                Decimal(str(horas))
                * Decimal(str(valor_curso.precio_hora))
            )

        else:
            monto_total = Decimal('0')

        return monto_total.quantize(
            Decimal('1'),
            rounding=ROUND_HALF_UP
        )

    def validate(self, data):

        if self.instance:
            campos_permitidos = {
                'numero_recibo',
                'monto_pagado',
            }

            campos_recibidos = set(
                self.initial_data.keys()
            )

            campos_no_permitidos = (
                campos_recibidos - campos_permitidos
            )

            if campos_no_permitidos:
                raise serializers.ValidationError({
                    'error': (
                        'Durante la edición solamente se puede '
                        'modificar el número de recibo y el monto.'
                    )
                })

            numero_recibo = data.get(
                'numero_recibo',
                self.instance.numero_recibo,
            )

            monto_pagado = data.get(
                'monto_pagado',
                self.instance.monto_pagado,
            )

            if not str(numero_recibo or '').strip():
                raise serializers.ValidationError({
                    'numero_recibo': (
                        'Debe ingresar el número de recibo.'
                    )
                })

            if monto_pagado is None:
                raise serializers.ValidationError({
                    'monto_pagado': (
                        'Debe ingresar el monto pagado.'
                    )
                })

            if monto_pagado < 0:
                raise serializers.ValidationError({
                    'monto_pagado': (
                        'El monto no puede ser negativo.'
                    )
                })

            if (
                self.instance.tipo_pago != 'beneficio'
                and monto_pagado <= 0
            ):
                raise serializers.ValidationError({
                    'monto_pagado': (
                        'El monto debe ser mayor a cero.'
                    )
                })

            matricula = self.instance.matricula

            monto_total = self.calcular_monto_total(
                matricula
            )

            total_otros_recibos = (
                Recibo.objects
                .filter(matricula=matricula)
                .exclude(id=self.instance.id)
                .aggregate(
                    total=models.Sum('monto_pagado')
                )['total']
                or Decimal('0.00')
            )

            monto_maximo = max(
                monto_total - total_otros_recibos,
                Decimal('0.00'),
            )

            if monto_pagado > monto_maximo:
                raise serializers.ValidationError({
                    'monto_pagado': (
                        'El monto no puede ser mayor a lo que '
                        'corresponde pagar en esta matrícula. '
                        f'Máximo permitido para este recibo: '
                        f'C${monto_maximo}.'
                    )
                })

            return data

        matricula = (
            data.get('matricula')
            or getattr(
                self.instance,
                'matricula',
                None,
            )
        )

        if not matricula:
            raise serializers.ValidationError({
                'matricula': (
                    'Debe seleccionar una matrícula.'
                )
            })

        if matricula.estado in [
            'cancelado',
            'finalizado',
        ]:
            raise serializers.ValidationError({
                'matricula': (
                    'No se pueden registrar pagos en una '
                    'matrícula cancelada o finalizada.'
                )
            })

        recibos_previos = Recibo.objects.filter(
            matricula=matricula
        )

        if self.instance:
            recibos_previos = recibos_previos.exclude(
                id=self.instance.id
            )

        tipo_pago = data.get(
            'tipo_pago',
            getattr(
                self.instance,
                'tipo_pago',
                None,
            )
        )

        monto_pagado = data.get(
            'monto_pagado',
            getattr(
                self.instance,
                'monto_pagado',
                Decimal('0.00'),
            )
        ) or Decimal('0.00')

        if monto_pagado < 0:
            raise serializers.ValidationError({
                'monto_pagado': (
                    'El monto no puede ser negativo.'
                )
            })

        monto_total = self.calcular_monto_total(
            matricula
        )

        total_pagado_previo = (
            recibos_previos.aggregate(
                total=models.Sum('monto_pagado')
            )['total']
            or Decimal('0.00')
        )

        saldo_pendiente = (
            monto_total - total_pagado_previo
        )

        if (
            not self.instance
            and recibos_previos.count() >= 2
        ):
            raise serializers.ValidationError(
                'Esta matrícula ya tiene los dos recibos '
                'permitidos.'
            )

        if (
            tipo_pago != 'beneficio'
            and monto_pagado <= 0
        ):
            raise serializers.ValidationError({
                'monto_pagado': (
                    'El monto debe ser mayor a cero.'
                )
            })

        if tipo_pago == 'completo':
            tiene_pago_final = (
                recibos_previos.filter(
                    tipo_pago__in=[
                        'completo',
                        'beneficio',
                    ]
                ).exists()
            )

            if tiene_pago_final:
                raise serializers.ValidationError(
                    'Esta matrícula ya tiene un pago '
                    'completo o beneficio registrado.'
                )

            anticipos_previos = (
                recibos_previos.filter(
                    tipo_pago='anticipo'
                )
            )

            monto_requerido = (
                saldo_pendiente
                if anticipos_previos.exists()
                else monto_total
            )

            montos_permitidos = {
                monto_requerido,
            }

            if monto_pagado not in montos_permitidos:
                raise serializers.ValidationError({
                    'monto_pagado': (
                        'El pago debe cubrir exactamente '
                        f'C${monto_requerido}.'
                    )
                })

        elif tipo_pago == 'anticipo':
            tiene_pago_final = (
                recibos_previos.filter(
                    tipo_pago__in=[
                        'completo',
                        'beneficio',
                    ]
                ).exists()
            )

            if tiene_pago_final:
                raise serializers.ValidationError(
                    'Esta matrícula ya está pagada '
                    'completamente.'
                )

            anticipos_previos = (
                recibos_previos.filter(
                    tipo_pago='anticipo'
                )
            )

            cantidad_anticipos = (
                anticipos_previos.count()
            )

            if cantidad_anticipos >= 1:
                if monto_pagado != saldo_pendiente:
                    raise serializers.ValidationError({
                        'monto_pagado': (
                            'El segundo anticipo debe ser '
                            'exactamente el saldo pendiente: '
                            f'C${saldo_pendiente}.'
                        )
                    })

            else:
                if monto_pagado >= monto_total:
                    raise serializers.ValidationError({
                        'monto_pagado': (
                            'El primer anticipo debe ser '
                            'menor al total del curso: '
                            f'C${monto_total}.'
                        )
                    })

            if monto_pagado > saldo_pendiente:
                raise serializers.ValidationError({
                    'monto_pagado': (
                        'El monto excede el saldo '
                        f'pendiente: C${saldo_pendiente}.'
                    )
                })

        elif tipo_pago == 'beneficio':
            if recibos_previos.exists():
                raise serializers.ValidationError(
                    'La matrícula ya tiene pagos '
                    'registrados.'
                )

        return data



    def preparar_datos_curso(
        self,
        matricula,
        validated_data,
    ):
        valor_curso = self.obtener_valor_curso(
            matricula
        )

        validated_data['valor_curso'] = valor_curso

        if matricula.tipo_curso == 'Principiante':
            validated_data['cantidad'] = (
                valor_curso.cantidad_horas
            )

            validated_data['monto_unitario'] = (
                valor_curso.precio_total
            )

        elif matricula.tipo_curso in [
            'Intermedio',
            'Avanzado',
        ]:
            validated_data['cantidad'] = (
                matricula.horas_reforzamiento
            )

            validated_data['monto_unitario'] = (
                valor_curso.precio_hora
            )

        return validated_data

    @transaction.atomic
    def create(self, validated_data):
        matricula_original = validated_data[
            'matricula'
        ]

        try:
            matricula = (
                Matricula.objects
                .select_for_update()
                .get(
                    id=matricula_original.id
                )
            )
        except Matricula.DoesNotExist:
            raise serializers.ValidationError({
                'matricula': (
                    'La matrícula seleccionada '
                    'ya no existe.'
                )
            })

        validated_data['matricula'] = matricula

        # Se repiten las validaciones después de bloquear
        # la matrícula para evitar pagos simultáneos.
        validated_data = self.validate(
            validated_data
        )

        tipo_pago = validated_data.get(
            'tipo_pago'
        )

        monto_pagado = (
            validated_data.get('monto_pagado')
            or Decimal('0.00')
        )

        monto_total = self.calcular_monto_total(
            matricula
        )

        validated_data = self.preparar_datos_curso(
            matricula,
            validated_data,
        )

        if tipo_pago == 'beneficio':
            matricula.estado = 'matriculado'

            matricula.save(
                update_fields=['estado']
            )

            return Recibo.objects.create(
                **validated_data
            )

        if tipo_pago == 'completo':
            anticipos_previos = (
                Recibo.objects.filter(
                    matricula=matricula,
                    tipo_pago='anticipo',
                )
            )

            # El segundo recibo reemplaza al anticipo.
            if anticipos_previos.exists():
                anticipos_previos.delete()

            validated_data['tipo_pago'] = (
                'completo'
            )

            validated_data['monto_pagado'] = (
                monto_total
            )

            matricula.estado = 'matriculado'

            matricula.save(
                update_fields=['estado']
            )

            return Recibo.objects.create(
                **validated_data
            )

        if tipo_pago == 'anticipo':
            total_pagado_anterior = (
                Recibo.objects.filter(
                    matricula=matricula
                ).aggregate(
                    total=models.Sum(
                        'monto_pagado'
                    )
                )['total']
                or Decimal('0.00')
            )

            nuevo_total_pagado = (
                total_pagado_anterior
                + monto_pagado
            )

            if nuevo_total_pagado >= monto_total:
                anticipos_previos = (
                    Recibo.objects.filter(
                        matricula=matricula,
                        tipo_pago='anticipo',
                    )
                )

                anticipos_previos.delete()

                validated_data['tipo_pago'] = (
                    'completo'
                )

                validated_data['monto_pagado'] = (
                    monto_total
                )

                matricula.estado = 'matriculado'

                matricula.save(
                    update_fields=['estado']
                )

            else:
                validated_data['tipo_pago'] = (
                    'anticipo'
                )

                if matricula.estado != 'pendiente':
                    matricula.estado = 'pendiente'

                    matricula.save(
                        update_fields=['estado']
                    )

            return Recibo.objects.create(
                **validated_data
            )

        return Recibo.objects.create(
            **validated_data
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        numero_recibo = validated_data.get(
            'numero_recibo',
            instance.numero_recibo,
        )

        monto_pagado = validated_data.get(
            'monto_pagado',
            instance.monto_pagado,
        )

        instance.numero_recibo = (
            str(numero_recibo).strip()
        )

        instance.monto_pagado = monto_pagado

        instance.save(
            update_fields=[
                'numero_recibo',
                'monto_pagado',
            ]
        )

        if instance.matricula.estado != 'finalizado':
            self.actualizar_estado_matricula(
                instance.matricula
            )

        return instance

    def actualizar_estado_matricula(
        self,
        matricula,
    ):
        if not matricula:
            return

        tiene_beneficio = matricula.recibos.filter(
            tipo_pago='beneficio'
        ).exists()

        if tiene_beneficio:
            if matricula.estado != 'matriculado':
                matricula.estado = 'matriculado'

                matricula.save(
                    update_fields=['estado']
                )

            return

        monto_total = self.calcular_monto_total(
            matricula
        )

        total_pagado = (
            matricula.recibos.aggregate(
                total=models.Sum('monto_pagado')
            )['total']
            or Decimal('0.00')
        )

        if total_pagado >= monto_total:
            nuevo_estado = 'matriculado'
        else:
            nuevo_estado = 'pendiente'

        if matricula.estado != nuevo_estado:
            matricula.estado = nuevo_estado

            matricula.save(
                update_fields=['estado']
            )

class CalendarioSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(source='matricula.estudiante.cedula', read_only=True)
    instructor_nombre = serializers.SerializerMethodField()
    instructor_telefono = serializers.SerializerMethodField()
    horario = serializers.CharField(source='matricula.horario', read_only=True)
    tipo_curso = serializers.CharField(source='matricula.tipo_curso', read_only=True)
    modalidad = serializers.CharField(source='matricula.modalidad', read_only=True)
    categoria = serializers.CharField(source='matricula.categoria.nombre', read_only=True)

    class Meta:
        model = Calendario
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"

    def get_instructor_nombre(self, obj):
        if not obj.instructor:
            return ''

        nombre = (
            f"{obj.instructor.nombre or ''} "
            f"{obj.instructor.apellido or ''}"
        ).strip()

        return (
            nombre
            or f'Instructor {obj.instructor.id}'
        )

    def get_instructor_telefono(self, obj):
        if not obj.instructor:
            return ""

        return str(
            obj.instructor.numero_telefono or ""
        ).strip()

    def validate(self, data):
        matricula = data.get('matricula') or getattr(self.instance, 'matricula', None)

        if matricula:
            if matricula.estado == 'finalizado':
                raise serializers.ValidationError(
                    'No se puede asignar horario a una matrícula finalizada.'
                )

            if not matricula.estudiante.usuarios.filter(rol__nombre__iexact='estudiante').exists():
                raise serializers.ValidationError(
                    'No se puede asignar horario porque el estudiante todavía no tiene usuario creado.'
                )

        return data


class CrearBloqueCitasSerializer(serializers.Serializer):
    instructor_id = serializers.IntegerField()
    matricula_id = serializers.IntegerField()
    fecha_inicio = serializers.DateField()
    horas_por_dia = serializers.IntegerField(default=2, required=False)

    def validate(self, data):
        try:
            matricula = Matricula.objects.select_related('estudiante').get(
                pk=data['matricula_id']
            )
        except Matricula.DoesNotExist:
            raise serializers.ValidationError('Matrícula no encontrada.')

        if matricula.estado == 'finalizado':
            raise serializers.ValidationError(
                'No se puede asignar horario a una matrícula finalizada.'
            )

        if not matricula.estudiante.usuarios.filter(rol__nombre__iexact='estudiante').exists():
            raise serializers.ValidationError(
                'No se puede asignar horario porque el estudiante todavía no tiene usuario creado.'
            )

        es_extraordinario = str(matricula.modalidad).lower() == 'extraordinario'
        es_finde = data['fecha_inicio'].weekday() >= 5

        if es_extraordinario and not es_finde:
            raise serializers.ValidationError(
                'Curso extraordinario: la fecha de inicio debe ser sábado o domingo.'
            )

        if not es_extraordinario and es_finde:
            raise serializers.ValidationError(
                'Curso regular: la fecha de inicio no puede ser sábado o domingo.'
            )

        if Calendario.objects.filter(matricula=matricula).exists():
            raise serializers.ValidationError(
                'Esta matrícula ya tiene clases asignadas.'
            )

        return data

class CrearCalendarioManualSerializer(serializers.Serializer):
    instructor_id = serializers.IntegerField()
    matricula_id = serializers.IntegerField()
    fechas = serializers.ListField(
        child=serializers.DateField(),
        allow_empty=False
    )
    horas_por_dia = serializers.IntegerField(default=2, required=False)

    def validate(self, data):
        try:
            matricula = Matricula.objects.select_related('estudiante').get(
                pk=data['matricula_id']
            )
        except Matricula.DoesNotExist:
            raise serializers.ValidationError('Matrícula no encontrada.')

        if matricula.estado == 'finalizado':
            raise serializers.ValidationError(
                'No se puede asignar horario a una matrícula finalizada.'
            )

        if not matricula.estudiante.usuarios.filter(rol__nombre__iexact='estudiante').exists():
            raise serializers.ValidationError(
                'No se puede asignar horario porque el estudiante todavía no tiene usuario creado.'
            )

        modalidad = str(matricula.modalidad or '').strip().lower()

        if modalidad != 'mixto':
            raise serializers.ValidationError(
                'La asignación manual solo está permitida para modalidad Mixto.'
            )

        horas_por_dia = int(data.get('horas_por_dia') or 2)

        if horas_por_dia <= 0:
            raise serializers.ValidationError(
                'Las horas por día deben ser mayores a cero.'
            )

        fechas = data.get('fechas') or []

        if len(fechas) != len(set(fechas)):
            raise serializers.ValidationError(
                'No puede seleccionar fechas repetidas.'
            )

        if Calendario.objects.filter(matricula=matricula).exists():
            raise serializers.ValidationError(
                'Esta matrícula ya tiene clases asignadas.'
            )

        if matricula.tipo_curso in ['Intermedio', 'Avanzado']:
            horas_totales = int(
                matricula.horas_reforzamiento or 0
            )

            if horas_totales <= 0:
                raise serializers.ValidationError(
                    'La matrícula no tiene horas asignadas para este curso.'
                )

            if matricula.incluye_examen_policial:
                horas_totales -= 2

        else:
            # Principiante continúa exactamente como está.
            horas_totales = 16

        num_clases = int(horas_totales) // horas_por_dia

        if int(horas_totales) % horas_por_dia != 0:
            num_clases += 1

        if len(fechas) != num_clases:
            raise serializers.ValidationError(
                f'Debe seleccionar exactamente {num_clases} fecha(s) para completar {horas_totales} hora(s).'
            )

        data['num_clases'] = num_clases
        return data

class AsistenciaSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(
        source='As_estudiante.cedula',
        read_only=True
    )

    calendario_id = serializers.IntegerField(
        source='As_calendario.id',
        read_only=True
    )

    fecha = serializers.DateField(
        source='As_calendario.fecha',
        read_only=True
    )

    hora_inicio = serializers.TimeField(
        source='As_calendario.hora_inicio',
        read_only=True
    )

    hora_fin = serializers.TimeField(
        source='As_calendario.hora_fin',
        read_only=True
    )

    numero_clase = serializers.IntegerField(
        source='As_calendario.numero_clase',
        read_only=True
    )

    instructor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Asistencia
        fields = [
            'id',
            'As_estudiante',
            'As_calendario',
            'calendario_id',
            'estado',
            'observacion',
            'justificado_por_admin',
            'km_inicial',
            'km_final',
            'km_recorridos',
            'fecha_registro',
            'fecha_actualizacion',
            'estudiante_nombre',
            'estudiante_cedula',
            'fecha',
            'hora_inicio',
            'hora_fin',
            'numero_clase',
            'instructor_nombre',
        ]

    def get_estudiante_nombre(self, obj):
        return f"{obj.As_estudiante.nombre} {obj.As_estudiante.apellido}"

    def get_instructor_nombre(self, obj):
        instructor = obj.As_calendario.instructor
        return f"{instructor.nombre} {instructor.apellido}"

class NotasSerializer(serializers.ModelSerializer):

    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(
        source='matricula.estudiante.cedula',
        read_only=True
    )

    instructor_nombre = serializers.SerializerMethodField()

    tipo_curso = serializers.CharField(
        source='matricula.tipo_curso',
        read_only=True
    )

    modalidad = serializers.CharField(
        source='matricula.modalidad',
        read_only=True
    )

    plan_nombre = serializers.CharField(
        source='plan_de_estudio.nombre',
        read_only=True
    )

    class Meta:
        model = Notas
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"

    def get_instructor_nombre(self, obj):
        return f"{obj.instructor.nombre} {obj.instructor.apellido}"

    def validate(self, data):
        matricula = data.get('matricula')
        nota = data.get('nota')
        tipo_nota = data.get('tipo_nota', 'practico')

        if not matricula:
            raise serializers.ValidationError({
                'matricula': 'Debe seleccionar una matrícula.'
            })

        if matricula.estado not in ['matriculado', 'finalizado']:
            raise serializers.ValidationError({
                'matricula': 'Solo se puede registrar nota a estudiantes matriculados o con plan finalizado.'
            })

        if nota is not None:
            try:
                nota_numero = Decimal(
                    str(nota).strip()
                )
            except (
                InvalidOperation,
                ValueError,
                TypeError,
            ):
                raise serializers.ValidationError({
                    'nota': 'La nota debe ser numérica.'
                })

            if not nota_numero.is_finite():
                raise serializers.ValidationError({
                    'nota': 'La nota debe ser un número válido.'
                })

            if nota_numero < 0 or nota_numero > 100:
                raise serializers.ValidationError({
                    'nota': 'La nota debe estar entre 0 y 100.'
                })

            data['nota'] = format(
                nota_numero.quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP,
                ),
                'f',
            )

        notas_previas = Notas.objects.filter(
            matricula=matricula,
            tipo_nota=tipo_nota
        )

        if self.instance:
            notas_previas = notas_previas.exclude(id=self.instance.id)

        if notas_previas.exists():
            raise serializers.ValidationError({
                'matricula': f'Este estudiante ya tiene registrada la nota del examen {tipo_nota}.'
            })

        return data

# serializers.py

class ProgresoTemaSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    usa_checks = serializers.SerializerMethodField()

    total_clases_diarias = serializers.SerializerMethodField()
    checks_diarios_completados = serializers.SerializerMethodField()
    porcentaje_clases_diarias = serializers.SerializerMethodField()

    estudiante_cedula = serializers.CharField(
        source='matricula.estudiante.cedula',
        read_only=True
    )

    tipo_curso = serializers.CharField(
        source='matricula.tipo_curso',
        read_only=True
    )

    tema_titulo = serializers.CharField(
        source='tema.titulo',
        read_only=True
    )

    subtemas = serializers.SerializerMethodField()
    subtemas_count = serializers.SerializerMethodField()

    tema_orden = serializers.IntegerField(
        source='orden_general',
        read_only=True
    )

    plan_estudio_id = serializers.IntegerField(
        source='tema.plan_estudio.id',
        read_only=True
    )

    plan_estudio_nombre = serializers.CharField(
        source='tema.plan_estudio.nombre',
        read_only=True
    )

    matricula_id = serializers.IntegerField(
        source='matricula.id',
        read_only=True
    )

    matricula_fecha = serializers.DateTimeField(
        source='matricula.fecha_registro',
        read_only=True
    )

    matricula_estado = serializers.CharField(
        source='matricula.estado',
        read_only=True
    )

    ambos_checks = serializers.BooleanField(
        source='ambos_checks_completados',
        read_only=True
    )

    modo_diario = serializers.SerializerMethodField()
    clase_actual_id = serializers.SerializerMethodField()
    fecha_clase_actual = serializers.SerializerMethodField()
    hora_inicio_clase = serializers.SerializerMethodField()
    habilitado_hoy = serializers.SerializerMethodField()
    estudiante_completado_hoy = serializers.SerializerMethodField()
    instructor_completado_hoy = serializers.SerializerMethodField()
    completado_hoy = serializers.SerializerMethodField()

    class Meta:
        model = ProgresoTema
        fields = [
            'id',
            'matricula',
            'tema',
            'orden_general',
            'desbloqueado',
            'estudiante_completado',
            'instructor_completado',
            'completado',
            'ambos_checks',
            'fecha_estudiante',
            'fecha_instructor',
            'fecha_admin_edit',
            'estudiante_nombre',
            'estudiante_cedula',
            'tipo_curso',
            'usa_checks',
            'tema_titulo',
            'subtemas',
            'subtemas_count',
            'tema_orden',
            'plan_estudio_id',
            'plan_estudio_nombre',
            'matricula_id',
            'matricula_fecha',
            'matricula_estado',
            'modo_diario',
            'clase_actual_id',
            'fecha_clase_actual',
            'hora_inicio_clase',
            'habilitado_hoy',
            'estudiante_completado_hoy',
            'instructor_completado_hoy',
            'completado_hoy',
            'total_clases_diarias',
            'checks_diarios_completados',
            'porcentaje_clases_diarias',
        ]

        read_only_fields = [
            'fecha_estudiante',
            'fecha_instructor',
            'fecha_admin_edit',
        ]

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre or ''} {estudiante.apellido or ''}".strip()

    def obtener_subtemas_activos(self, obj):
        if not obj.tema:
            return []

        cache = getattr(
            obj,
            '_subtemas_activos_serializer',
            None
        )

        if cache is not None:
            return cache

        subtemas = sorted(
            (
                subtema
                for subtema in obj.tema.subtemas.all()
                if subtema.activo
            ),
            key=lambda subtema: (
                subtema.orden or 0,
                subtema.id,
            )
        )

        obj._subtemas_activos_serializer = subtemas

        return subtemas

    def get_subtemas(self, obj):
        return [
            {
                'id': subtema.id,
                'orden': subtema.orden,
                'titulo': subtema.titulo,
                'activo': subtema.activo,
            }
            for subtema
            in self.obtener_subtemas_activos(obj)
        ]

    def get_subtemas_count(self, obj):
        return len(
            self.obtener_subtemas_activos(obj)
        )

    def es_modo_diario(self, obj):
        return False

    def obtener_check_dia(self, obj):
        return getattr(obj, 'check_dia_actual', None)

    def obtener_clase_actual(self, obj):
        check_dia = self.obtener_check_dia(obj)

        if check_dia and check_dia.calendario:
            return check_dia.calendario

        return getattr(obj, 'calendario_actual', None)

    def get_modo_diario(self, obj):
        return self.es_modo_diario(obj)

    def get_clase_actual_id(self, obj):
        clase = self.obtener_clase_actual(obj)
        return clase.id if clase else None

    def get_fecha_clase_actual(self, obj):
        clase = self.obtener_clase_actual(obj)
        return clase.fecha if clase else None

    def get_hora_inicio_clase(self, obj):
        clase = self.obtener_clase_actual(obj)
        return clase.hora_inicio if clase else None

    def get_habilitado_hoy(self, obj):
        if not self.es_modo_diario(obj):
            return obj.desbloqueado

        return bool(getattr(obj, 'habilitado_hoy', False))

    def get_estudiante_completado_hoy(self, obj):
        if not self.es_modo_diario(obj):
            return obj.estudiante_completado

        check_dia = self.obtener_check_dia(obj)
        return check_dia.estudiante_completado if check_dia else False

    def get_instructor_completado_hoy(self, obj):
        if not self.es_modo_diario(obj):
            return obj.instructor_completado

        check_dia = self.obtener_check_dia(obj)
        return check_dia.instructor_completado if check_dia else False

    def get_completado_hoy(self, obj):
        if not self.es_modo_diario(obj):
            return obj.completado

        check_dia = self.obtener_check_dia(obj)
        return check_dia.completado if check_dia else False

    def obtener_clases_validas_diarias(self, obj):
        return Calendario.objects.filter(
            matricula=obj.matricula,
            es_examen=False
        ).exclude(
            estado='cancelada'
        )

    def get_total_clases_diarias(self, obj):
        if not self.es_modo_diario(obj):
            return None

        return self.obtener_clases_validas_diarias(obj).count()

    def get_checks_diarios_completados(self, obj):
        if not self.es_modo_diario(obj):
            return None

        clases = self.obtener_clases_validas_diarias(obj)

        return ProgresoClaseTema.objects.filter(
            progreso_tema=obj,
            calendario__in=clases,
            estudiante_completado=True,
            instructor_completado=True,
            completado=True
        ).count()

    def get_porcentaje_clases_diarias(self, obj):
        if not self.es_modo_diario(obj):
            return None

        total = self.get_total_clases_diarias(obj)

        if not total:
            return 0

        completados = self.get_checks_diarios_completados(obj)

        return round((completados / total) * 100)

    def get_usa_checks(self, obj):
        tipo_curso = str(
            getattr(obj.matricula, 'tipo_curso', '') or ''
        ).strip().lower()

        return tipo_curso == 'principiante'

class NotificacionSerializer(serializers.ModelSerializer):
    """Serializer para notificaciones del administrador"""

    estudiante_nombre = serializers.CharField(source='estudiante.username', read_only=True)
    tema_titulo = serializers.CharField(source='tema.titulo', read_only=True, allow_null=True)

    class Meta:
        model = Notificacion  # Asegúrate que el modelo existe
        fields = '__all__'
        read_only_fields = ['fecha_creacion']


class HistorialPlanEstudioSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)

    progreso_tema_titulo = serializers.CharField(
        source='progreso_tema.tema.titulo',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = HistorialPlanEstudio
        fields = '__all__'
        read_only_fields = ['fecha']

class MarcarTemaSerializer(serializers.Serializer):
    progreso_id = serializers.IntegerField()
    tipo = serializers.ChoiceField(choices=['estudiante', 'instructor', 'admin_estudiante', 'admin_instructor'])

class OpcionPreguntaExamenTeoricoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpcionPreguntaExamenTeorico
        fields = [
            'id',
            'texto',
            'es_correcta',
        ]

class PreguntaExamenTeoricoSerializer(serializers.ModelSerializer):
    opciones = OpcionPreguntaExamenTeoricoSerializer(many=True)

    class Meta:
        model = PreguntaExamenTeorico
        fields = [
            'id',
            'texto',

            'activa',
            'fecha_creacion',
            'opciones',
        ]
        read_only_fields = ['fecha_creacion']

    def validate(self, data):
        opciones = data.get('opciones', [])

        if len(opciones) < 2:
            raise serializers.ValidationError({
                'opciones': 'Debe agregar al menos dos opciones de respuesta.'
            })

        correctas = [
            opcion for opcion in opciones
            if opcion.get('es_correcta') is True
        ]

        if len(correctas) != 1:
            raise serializers.ValidationError({
                'opciones': 'Debe marcar exactamente una opción como correcta.'
            })

        return data

    def create(self, validated_data):
        opciones_data = validated_data.pop('opciones')

        pregunta = PreguntaExamenTeorico.objects.create(**validated_data)

        for opcion_data in opciones_data:
            OpcionPreguntaExamenTeorico.objects.create(
                pregunta=pregunta,
                **opcion_data
            )

        return pregunta

    def update(self, instance, validated_data):
        opciones_data = validated_data.pop('opciones', None)

        instance.texto = validated_data.get('texto', instance.texto)
        instance.activa = validated_data.get('activa', instance.activa)

        instance.save()

        if opciones_data is not None:
            instance.opciones.all().delete()

            for opcion_data in opciones_data:
                OpcionPreguntaExamenTeorico.objects.create(
                    pregunta=instance,
                    **opcion_data
                )

        return instance

class ExamenTeoricoSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(
        source='matricula.estudiante.cedula',
        read_only=True
    )
    tipo_curso = serializers.CharField(
        source='matricula.tipo_curso',
        read_only=True
    )
    instructor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ExamenTeorico
        fields = [
            'id',
            'matricula',
            'estudiante_nombre',
            'estudiante_cedula',
            'tipo_curso',
            'habilitado_por',
            'instructor_nombre',
            'estado',
            'nota',
            'fecha_habilitado',
            'fecha_realizado',
        ]
        read_only_fields = [
            'habilitado_por',
            'estado',
            'nota',
            'fecha_habilitado',
            'fecha_realizado',
        ]

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"

    def get_instructor_nombre(self, obj):
        if not obj.habilitado_por:
            return None

        return f"{obj.habilitado_por.nombre} {obj.habilitado_por.apellido}".strip()

class OpcionExamenEstudianteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpcionPreguntaExamenTeorico
        fields = [
            'id',
            'texto',
        ]

class PreguntaExamenEstudianteSerializer(serializers.ModelSerializer):
    opciones = OpcionExamenEstudianteSerializer(many=True, read_only=True)

    class Meta:
        model = PreguntaExamenTeorico
        fields = [
            'id',
            'texto',
            'opciones',
        ]

class RespuestaIndividualExamenSerializer(
    serializers.Serializer
):
    pregunta_id = serializers.IntegerField(
        min_value=1,
    )

    opcion_id = serializers.IntegerField(
        min_value=1,
    )

class RespuestaEnviarExamenSerializer(
    serializers.Serializer
):
    respuestas = RespuestaIndividualExamenSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_respuestas(self, respuestas):
        preguntas_ids = [
            respuesta['pregunta_id']
            for respuesta in respuestas
        ]

        if len(preguntas_ids) != len(set(preguntas_ids)):
            raise serializers.ValidationError(
                'Una pregunta fue respondida más de una vez.'
            )

        return respuestas

class RespuestaExamenTeoricoSerializer(serializers.ModelSerializer):
    pregunta_texto = serializers.CharField(
        source='pregunta.texto',
        read_only=True,
    )

    opcion_texto = serializers.CharField(
        source='opcion_seleccionada.texto',
        read_only=True,
    )

    intento_id = serializers.IntegerField(
        source='intento.id',
        read_only=True,
    )

    numero_intento = serializers.IntegerField(
        source='intento.numero_intento',
        read_only=True,
    )

    class Meta:
        model = RespuestaExamenTeorico

        fields = [
            'id',
            'examen',
            'intento',
            'intento_id',
            'numero_intento',
            'pregunta',
            'pregunta_texto',
            'opcion_seleccionada',
            'opcion_texto',
            'correcta',
            'fecha_respuesta',
        ]

        read_only_fields = [
            'id',
            'examen',
            'intento',
            'intento_id',
            'numero_intento',
            'pregunta',
            'pregunta_texto',
            'opcion_seleccionada',
            'opcion_texto',
            'correcta',
            'fecha_respuesta',
        ]

class PagoInstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoInstructor
        fields = '__all__'

class CargoInstitucionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CargoInstitucional
        fields = '__all__'