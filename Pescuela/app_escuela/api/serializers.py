# app_escuela/api/serializers.py

from decimal import Decimal
from rest_framework import serializers
from django.db import models

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
from ..models import ProgresoTema, HistorialPlanEstudio,Notificacion

from ..models import PlanEstudio, SubtemaPlanEstudio, ProgresoTema

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
            'matricula_id',
            'instructor_id',
            'estudiante_nombre',
            'instructor_nombre',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False}
        }

    def get_estudiante_nombre(self, obj):
        if obj.estudiante:
            return f"{obj.estudiante.nombre or ''} {obj.estudiante.apellido or ''}".strip()
        return None

    def get_instructor_nombre(self, obj):
        if obj.instructor:
            return f"{obj.instructor.nombre or ''} {obj.instructor.apellido or ''}".strip()
        return None

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

        subtemas_activos = instance.subtemas.filter(
            activo=True
        ).order_by(
            'orden',
            'id'
        )

        data['subtemas'] = SubtemaPlanEstudioSerializer(
            subtemas_activos,
            many=True
        ).data

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

        temas_activos = instance.temas.filter(
            activo=True
        ).order_by(
            'orden',
            'id'
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

    class Meta:
        model = Estudiante
        fields = '__all__'
        read_only_fields = ['codigo_estudiante']

    def get_usuario_data(self, obj):
        usuario = obj.usuarios.filter(rol__nombre__iexact='estudiante').first()

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

class InstructorSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()
    categoria_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = '__all__'
    def get_nombre_completo(self, obj):
        nombre = f"{obj.nombre or ''} {obj.apellido or ''}".strip()
        return nombre or f"Instructor {obj.id}"
    

    def get_categoria_nombre(self, obj):
        return obj.categoria_instructor or ""


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

    class Meta:
        model = Matricula
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        return f"{obj.estudiante.nombre} {obj.estudiante.apellido}"

    def get_tiene_usuario(self, obj):
        return obj.estudiante.usuarios.exists()

    def create(self, validated_data):
        tipo_curso = validated_data.get('tipo_curso')

        if tipo_curso == 'Principiante':
            tipos_planes = ['Principiante']
        elif tipo_curso == 'Intermedio':
            tipos_planes = ['Intermedio']
        elif tipo_curso == 'Avanzado':
            tipos_planes = ['Avanzado']
        else:
            tipos_planes = [tipo_curso]

        planes = list(
            PlanEstudio.objects.filter(
                tipo_curso__in=tipos_planes,
                activo=True
            )
        )

        planes.sort(
            key=lambda plan: (
                tipos_planes.index(plan.tipo_curso),
                plan.id
            )
        )

        if not planes:
            raise serializers.ValidationError({
                'plan_de_estudio': f'No existen planes de estudio activos para el curso {tipo_curso}.'
            })

        plan_principal = next(
            (plan for plan in planes if plan.tipo_curso == tipo_curso),
            planes[0]
        )

        validated_data['plan_de_estudio'] = plan_principal

        matricula = Matricula.objects.create(**validated_data)

        orden_general = 1

        for plan in planes:
            temas = TemaPlanEstudio.objects.filter(
                plan_estudio=plan,
                activo=True
            ).order_by(
                'orden',
                'id'
            )

            for tema in temas:
                ProgresoTema.objects.create(
                    matricula=matricula,
                    tema=tema,
                    orden_general=orden_general,
                    desbloqueado=False,
                    estudiante_completado=False,
                    instructor_completado=False,
                    completado=False,
                )

                orden_general += 1

        return matricula

class ReciboSerializer(serializers.ModelSerializer):
    matricula_data = MatriculaSerializer(source='matricula', read_only=True)
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(source='matricula.estudiante.cedula', read_only=True)

    class Meta:
        model = Recibo
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"

    def obtener_valor_curso(self, matricula):
        valor_curso = ValorCurso.objects.filter(
            tipo_curso=matricula.tipo_curso,
            activo=True
        ).order_by('-fecha_modificacion').first()

        if not valor_curso:
            raise serializers.ValidationError(
                f'No existe un valor activo para el curso {matricula.tipo_curso}.'
            )

        return valor_curso


    def calcular_monto_total(self, matricula):
        valor_curso = self.obtener_valor_curso(matricula)

        if matricula.tipo_curso == 'Principiante':
           return Decimal(valor_curso.precio_total).quantize(Decimal('1'))

        if matricula.tipo_curso in ['Intermedio', 'Avanzado']:
            horas = matricula.horas_reforzamiento

            if not horas:
                raise serializers.ValidationError(
                    f'El curso {matricula.tipo_curso} requiere horas.'
                )

            return (Decimal(horas) * valor_curso.precio_hora).quantize(Decimal('1'))

        return Decimal('0')

    def validate(self, data):
        matricula = data.get('matricula') or getattr(self.instance, 'matricula', None)

        if not matricula:
            raise serializers.ValidationError({
                'matricula': 'Debe seleccionar una matrícula.'
            })

        if matricula.estado in ['cancelado', 'finalizado']:
            raise serializers.ValidationError({
                'matricula': 'No se pueden registrar pagos en una matrícula cancelada o finalizada.'
            })

        recibos_previos = Recibo.objects.filter(matricula=matricula)
        if self.instance:
            recibos_previos = recibos_previos.exclude(id=self.instance.id)

        tipo_pago = data.get('tipo_pago')
        monto_pagado = data.get('monto_pagado') or Decimal('0')
        monto_total = self.calcular_monto_total(matricula)

        total_pagado_previo = recibos_previos.aggregate(
            total=models.Sum('monto_pagado')
        )['total'] or Decimal('0')

        saldo_pendiente = monto_total - total_pagado_previo

        if tipo_pago != 'beneficio' and monto_pagado <= 0:
            raise serializers.ValidationError({
                'monto_pagado': 'El monto debe ser mayor a cero.'
            })

        # COMPLETO
        if tipo_pago == 'completo':
            tiene_pago_completo = recibos_previos.filter(
                tipo_pago__in=['completo', 'beneficio']
            ).exists()
            if tiene_pago_completo:
                raise serializers.ValidationError(
                    'Esta Matrícula ya tiene un Pago Completo o Beneficio Registrado.'
                )
            if (monto_pagado != monto_total) :
                raise serializers.ValidationError(
                    f'El pago completo debe cubrir el total exacto: C${monto_total}.'
                )

        # ANTICIPO
        elif tipo_pago == 'anticipo':
            anticipos_previos = recibos_previos.filter(tipo_pago='anticipo')
            cantidad_anticipos = anticipos_previos.count()

            if cantidad_anticipos >= 1:
                if monto_pagado != saldo_pendiente:
                    raise serializers.ValidationError({
                        'monto_pagado':
                            f'El segundo anticipo debe ser exactamente el saldo pendiente: C${saldo_pendiente}.'
                    })

            else:
                if monto_pagado >= monto_total:
                    raise serializers.ValidationError({
                        'monto_pagado':
                            f'El primer anticipo debe ser menor al total del curso: C${monto_total}.'
                    })

            if monto_pagado > saldo_pendiente:
                raise serializers.ValidationError({
                    'monto_pagado':
                        f'El monto excede el saldo pendiente: C${saldo_pendiente}.'
                })

        # BENEFICIO
        elif tipo_pago == 'beneficio':
            if recibos_previos.exists():
                raise serializers.ValidationError(
                    'La matrícula ya tiene pagos registrados.'
                )

        return data

    def create(self, validated_data):
        matricula = validated_data['matricula']
        tipo_pago = validated_data.get('tipo_pago')
        monto_pagado = validated_data.get('monto_pagado') or Decimal('0')
        monto_total = self.calcular_monto_total(matricula)

        valor_curso = self.obtener_valor_curso(matricula)

        validated_data['valor_curso'] = valor_curso

        if matricula.tipo_curso == 'Principiante':
            validated_data['cantidad'] = valor_curso.cantidad_horas
            validated_data['monto_unitario'] = valor_curso.precio_total
        elif matricula.tipo_curso in ['Intermedio', 'Avanzado']:
            validated_data['cantidad'] = matricula.horas_reforzamiento
            validated_data['monto_unitario'] = valor_curso.precio_hora
        else:
            validated_data['cantidad'] = 1
            validated_data['monto_unitario'] = Decimal('0')

        validated_data['estado'] = 'pagado'

        # ==============================================
        # CASO 1: BENEFICIO
        # ==============================================
        if tipo_pago == 'beneficio':
            matricula.estado = 'matriculado'
            matricula.save(update_fields=['estado'])
            print(f"✅ BENEFICIO: Matrícula {matricula.id} cambiada a MATRICULADO")
            return Recibo.objects.create(**validated_data)

        # ==============================================
        # CASO 2: COMPLETO DIRECTO
        # ==============================================
        elif tipo_pago == 'completo':
            matricula.estado = 'matriculado'
            matricula.save(update_fields=['estado'])
            print(f"✅ COMPLETO: Matrícula {matricula.id} cambiada a MATRICULADO")
            return Recibo.objects.create(**validated_data)

        # ==============================================
        # CASO 3: ANTICIPO
        # ==============================================
                # ==============================================
        # CASO 3: ANTICIPO
        # ==============================================
        elif tipo_pago == 'anticipo':
            # Sumar TODOS los pagos anteriores de esta matrícula
            total_pagado_anterior = Recibo.objects.filter(
                matricula=matricula
            ).aggregate(
                total=models.Sum('monto_pagado')
            )['total'] or Decimal('0')

            # Saldo que quedaba pendiente ANTES de este pago
            saldo_antes_de_este_pago = monto_total - total_pagado_anterior
            nuevo_total_pagado = total_pagado_anterior + monto_pagado

            print(f"\n=== PROCESANDO ANTICIPO ===")
            print(f"Totala apagar: {monto_total}")
            print(f"Total pagado antes: {total_pagado_anterior}")
            print(f"Monto nuevo: {monto_pagado}")
            print(f"Saldo pendiente antes: {saldo_antes_de_este_pago}")
            print(f"Nuevo total pagado: {nuevo_total_pagado}")
            print(f"Monto total curso: {monto_total}")

            # Completa si: el total acumulado llega al monto del curso
            # O si este pago cubre exactamente el saldo que quedaba
            pago_completa_curso = (
                nuevo_total_pagado >= monto_total or
                monto_pagado >= saldo_antes_de_este_pago
            )

            if pago_completa_curso:
                print(f"✅ ANTICIPO COMPLETA EL CURSO")

                # Eliminar todos los anticipos previos
                anticipos_previos = Recibo.objects.filter(
                    matricula=matricula,
                    tipo_pago='anticipo'
                )
                cantidad = anticipos_previos.count()
                anticipos_previos.delete()
                print(f"   - {cantidad} anticipo(s) anterior(es) eliminado(s)")

                # Convertir este recibo a COMPLETO con el total real acumulado
                validated_data['tipo_pago'] = 'completo'
                validated_data['monto_pagado'] = nuevo_total_pagado

                matricula.estado = 'matriculado'
                matricula.save(update_fields=['estado'])
                print(f"   - Matrícula {matricula.id} cambiada a MATRICULADO")

            else:
                saldo_restante = monto_total - nuevo_total_pagado
                print(f"⚠️ ANTICIPO PARCIAL - Saldo restante: C${saldo_restante}")
                validated_data['tipo_pago'] = 'anticipo'

            return Recibo.objects.create(**validated_data)

    def update(self, instance, validated_data):
        matricula = instance.matricula

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        self.actualizar_estado_matricula(matricula)
        return instance

    def actualizar_estado_matricula(self, matricula):
        if not matricula:
            return

        monto_total = self.calcular_monto_total(matricula)

        total_pagado = matricula.recibos.aggregate(
            total=models.Sum('monto_pagado')
        )['total'] or Decimal('0')

        print(f"\n=== RECALCULANDO MATRÍCULA {matricula.id} ===")
        print(f"Total pagado: {total_pagado}")
        print(f"Monto total: {monto_total}")

        if total_pagado >= monto_total:
            if matricula.estado != 'matriculado':
                matricula.estado = 'matriculado'
                matricula.save(update_fields=['estado'])
                print(f"✅ Estado cambiado a: MATRICULADO")
            else:
                print(f"ℹ️ Estado ya es MATRICULADO")
        else:
            if matricula.estado == 'matriculado':
                matricula.estado = 'pendiente'
                matricula.save(update_fields=['estado'])
                print(f"⚠️ Estado cambiado a: PENDIENTE")
            else:
                print(f"ℹ️ Estado se mantiene como: {matricula.estado}")


class CalendarioSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.SerializerMethodField()
    estudiante_cedula = serializers.CharField(source='matricula.estudiante.cedula', read_only=True)
    instructor_nombre = serializers.SerializerMethodField()
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
            return ""

        nombre = f"{obj.instructor.nombre or ''} {obj.instructor.apellido or ''}".strip()

        if nombre:
            return nombre

        usuario = obj.instructor.usuarios.first()

        if usuario:
            nombre_usuario = f"{usuario.first_name} {usuario.last_name}".strip()
            return nombre_usuario or usuario.username

        return f"Instructor {obj.instructor.id}"

    def validate(self, data):
        matricula = data.get('matricula') or getattr(self.instance, 'matricula', None)

        if matricula:
            if matricula.estado != 'matriculado':
                raise serializers.ValidationError(
                    'No se puede asignar horario porque la matrícula aún no está aprobada.'
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

        if matricula.estado != 'matriculado':
            raise serializers.ValidationError(
                'No se puede asignar horario porque la matrícula aún no está aprobada.'
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

# serializers.py - Modifica el NotasSerializer

# serializers.py - Asegúrate de que el serializer incluya instructor

# serializers.py

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
                nota_numero = float(nota)
            except ValueError:
                raise serializers.ValidationError({
                    'nota': 'La nota debe ser numérica.'
                })

            if nota_numero < 0 or nota_numero > 100:
                raise serializers.ValidationError({
                    'nota': 'La nota debe estar entre 0 y 100.'
                })

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
            'tema_titulo',
            'subtemas',
            'subtemas_count',
            'tema_orden',
            'plan_estudio_id',
            'plan_estudio_nombre',
            'matricula_id',
            'matricula_fecha',
            'matricula_estado',
        ]

        read_only_fields = [
            'fecha_estudiante',
            'fecha_instructor',
            'fecha_admin_edit',
        ]

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre or ''} {estudiante.apellido or ''}".strip()

    def get_subtemas(self, obj):
        if not obj.tema:
            return []

        subtemas = obj.tema.subtemas.filter(
            activo=True
        ).order_by(
            'orden',
            'id'
        )

        return [
            {
                'id': subtema.id,
                'orden': subtema.orden,
                'titulo': subtema.titulo,
                'activo': subtema.activo,
            }
            for subtema in subtemas
        ]

    def get_subtemas_count(self, obj):
        if not obj.tema:
            return 0

        return obj.tema.subtemas.filter(
            activo=True
        ).count()


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

class RespuestaEnviarExamenSerializer(serializers.Serializer):
    respuestas = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False
    )

    def validate_respuestas(self, respuestas):
        for respuesta in respuestas:
            if 'pregunta_id' not in respuesta:
                raise serializers.ValidationError(
                    'Cada respuesta debe incluir pregunta_id.'
                )

            if 'opcion_id' not in respuesta:
                raise serializers.ValidationError(
                    'Cada respuesta debe incluir opcion_id.'
                )

        return respuestas
    

class RespuestaExamenTeoricoSerializer(serializers.ModelSerializer):
    pregunta_texto = serializers.CharField(
        source='pregunta.texto',
        read_only=True
    )

    opcion_texto = serializers.CharField(
        source='opcion_seleccionada.texto',
        read_only=True
    )

    class Meta:
        model = RespuestaExamenTeorico
        fields = [
            'id',
            'examen',
            'pregunta',
            'pregunta_texto',
            'opcion_seleccionada',
            'opcion_texto',
            'correcta',
        ]
        read_only_fields = [
            'correcta',
        ]

class PagoInstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoInstructor
        fields = '__all__'

class CargoInstitucionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CargoInstitucional
        fields = '__all__'