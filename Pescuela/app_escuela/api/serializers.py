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
)


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
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False}
        }

    def validate(self, data):
        matricula_id = data.get('matricula_id')
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

        return data

    def create(self, validated_data):
        matricula_id = validated_data.pop('matricula_id', None)
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

        return usuario

    def update(self, instance, validated_data):
        validated_data.pop('matricula_id', None)
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class PlanEstudioSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanEstudio
        fields = '__all__'

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
    nombre = serializers.CharField(source='usuario.first_name', read_only=True)
    apellido = serializers.CharField(source='usuario.last_name', read_only=True)
    username = serializers.CharField(source='usuario.username', read_only=True)
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = '__all__'

    def get_nombre_completo(self, obj):
        if obj.usuario:
            nombre = f"{obj.usuario.first_name} {obj.usuario.last_name}".strip()
            return nombre or obj.usuario.username

        return f"Instructor {obj.id}"


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
    estudiante_contacto_emergencia = serializers.CharField(source='estudiante.en_caso_de_emergencia', read_only=True)
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
    categoria = serializers.CharField(source='matricula.categoria', read_only=True)

    class Meta:
        model = Calendario
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"

    def get_instructor_nombre(self, obj):
        if obj.instructor and obj.instructor.usuario:
            u = obj.instructor.usuario
            nombre = f"{u.first_name} {u.last_name}".strip()
            return nombre or u.username

        return ""

    def validate(self, data):
        matricula = data.get('matricula') or getattr(self.instance, 'matricula', None)

        if matricula:
            if matricula.estado != 'aprobado':
                raise serializers.ValidationError(
                    'No se puede asignar horario porque la matrícula aún no está aprobada.'
                )

            if not matricula.estudiante.usuario:
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

        if matricula.estado != 'aprobado':
            raise serializers.ValidationError(
                'No se puede asignar horario porque la matrícula aún no está aprobada.'
            )

        if not matricula.estudiante.usuario:
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
    fecha_clase = serializers.DateField(source='clase.fecha', read_only=True)
    numero_clase = serializers.IntegerField(source='clase.numero_clase', read_only=True)

    class Meta:
        model = Asistencia
        fields = '__all__'

    def get_estudiante_nombre(self, obj):
        estudiante = obj.clase.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"


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
        fields = [
            'id',
            'matricula',
            'instructor',
            'plan_de_estudio',
            'estudiante_nombre',
            'estudiante_cedula',
            'instructor_nombre',
            'plan_nombre',
            'tipo_curso',
            'modalidad',
            # 'nota',
            #'comentario',
        ]

    def get_estudiante_nombre(self, obj):
        estudiante = obj.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido}"

    def get_instructor_nombre(self, obj):
        return f"{obj.instructor.nombre} {obj.instructor.apellido}"