# app_escuela/api/views.py

from datetime import date, datetime, timedelta
from decimal import Decimal
from decimal import Decimal
from django.db import models
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers
import openpyxl
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models.functions import TruncMonth
from decimal import Decimal
from rest_framework import status
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as ExcelImage
import os

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
    PreguntaExamenTeorico,
    OpcionPreguntaExamenTeorico,
    ExamenTeorico,
    RespuestaExamenTeorico,
)

from .serializers import (
    RolSerializer,
    UserSerializer,
    EstudianteSerializer,
    InstructorSerializer,
    CategoriaVehiculoSerializer,
    MatriculaSerializer,
    ReciboSerializer,
    CalendarioSerializer,
    CrearBloqueCitasSerializer,
    AsistenciaSerializer,
    NotasSerializer,
    ValorCursoSerializer,
    PreguntaExamenTeoricoSerializer,
    ExamenTeoricoSerializer,
    PreguntaExamenEstudianteSerializer,
    RespuestaEnviarExamenSerializer,
    RespuestaExamenTeoricoSerializer,
)

from .serializers import (
     PlanEstudioSerializer, ProgresoTemaSerializer, 
     NotificacionSerializer
 )

from ..models import PlanEstudio, SubtemaPlanEstudio, ProgresoTema


def generar_progreso_plan(matricula):
    if not matricula.plan_de_estudio:
        return

    subtemas = SubtemaPlanEstudio.objects.filter(
        tema__plan_estudio=matricula.plan_de_estudio,
        activo=True,
        tema__activo=True
    ).order_by(
        'tema__orden',
        'orden',
        'id'
    )

    for index, subtema in enumerate(subtemas):
        ProgresoTema.objects.get_or_create(
            matricula=matricula,
            subtema=subtema,
            defaults={
                'desbloqueado': index == 0,
                'estudiante_completado': False,
                'instructor_completado': False,
                'completado': False,
            }
        )

def obtener_rango_horario(matricula):
    mapeo = {
        '06AM': ('06:00', '08:00'),
        '08AM': ('08:00', '10:00'),
        '10AM': ('10:00', '12:00'),
        '12PM': ('12:00', '14:00'),
        '04PM': ('16:00', '18:00'),
    }

    return mapeo.get(matricula.horario)


class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer
    permission_classes = [IsAuthenticated]


class CategoriaVehiculoViewSet(viewsets.ModelViewSet):
    queryset = CategoriaVehiculo.objects.all()
    serializer_class = CategoriaVehiculoSerializer
    permission_classes = [IsAuthenticated]


class EstudianteViewSet(viewsets.ModelViewSet):
    queryset = Estudiante.objects.all()
    serializer_class = EstudianteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Estudiante.objects.all().order_by('-id')
        buscar = self.request.query_params.get('buscar')

        if buscar:
            queryset = queryset.filter(
                Q(nombre__icontains=buscar) |
                Q(apellido__icontains=buscar) |
                Q(cedula__icontains=buscar)
            )

        return queryset

class PlanEstudioViewSet(viewsets.ModelViewSet):
    queryset = PlanEstudio.objects.prefetch_related(
        'temas',
        'temas__subtemas'
    ).all()

    serializer_class = PlanEstudioSerializer

    @action(detail=False, methods=['get'], url_path='tipos-curso')
    def tipos_curso(self, request):
        return Response([
            {'value': 'Principiante', 'label': 'Principiante'},
            {'value': 'Intermedio', 'label': 'Intermedio'},
            {'value': 'Avanzado', 'label': 'Avanzado'},
        ])

    @action(detail=True, methods=['get'], url_path='debug-temas')
    def debug_temas(self, request, pk=None):
        plan = self.get_object()
        temas = plan.temas.all()

        data = {
            'plan_id': plan.id,
            'plan_nombre': plan.nombre,
            'total_temas': temas.count(),
            'temas': [
                {
                    'id': tema.id,
                    'titulo': tema.titulo,
                    'activo': tema.activo,
                    'orden': tema.orden,
                    'subtemas_count': tema.subtemas.count()
                }
                for tema in temas
            ]
        }
        return Response(data)

class ValorCursoViewSet(viewsets.ModelViewSet):
    queryset = ValorCurso.objects.all().order_by('-fecha_modificacion')
    serializer_class = ValorCursoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ValorCurso.objects.all().order_by('-fecha_modificacion')
        activo = self.request.query_params.get('activo')
        tipo_curso = self.request.query_params.get('tipo_curso')

        if activo is not None:
            if activo.lower() == 'true':
                queryset = queryset.filter(activo=True)
            elif activo.lower() == 'false':
                queryset = queryset.filter(activo=False)

        if tipo_curso:
            queryset = queryset.filter(tipo_curso=tipo_curso)

        return queryset

class InstructorViewSet(viewsets.ModelViewSet):
    queryset = Instructor.objects.all()
    serializer_class = InstructorSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]


class MatriculaViewSet(viewsets.ModelViewSet):
    queryset = Matricula.objects.select_related('estudiante').all()
    serializer_class = MatriculaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Matricula.objects.select_related('estudiante').all().order_by('-id')
        buscar = self.request.query_params.get('buscar')
        estado = self.request.query_params.get('estado')

        if buscar:
            queryset = queryset.filter(
                Q(estudiante__cedula__icontains=buscar) |
                Q(estudiante__nombre__icontains=buscar) |
                Q(estudiante__apellido__icontains=buscar)
            )

        if estado:
            queryset = queryset.filter(estado=estado)

        return queryset

    @action(detail=False, methods=['get'], url_path='buscar-estudiante')
    def buscar_estudiante(self, request):
        q = request.query_params.get('q')

        if not q:
            return Response(
                {'error': 'Debe enviar un nombre o una cédula para buscar.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        estudiantes = Estudiante.objects.filter(
            Q(cedula__icontains=q) |
            Q(nombre__icontains=q) |
            Q(apellido__icontains=q)
        ).order_by('-id')[:10]

        resultados = []

        for estudiante in estudiantes:
            resultados.append({
                'id': estudiante.id,
                'nombre': estudiante.nombre,
                'apellido': estudiante.apellido,
                'cedula': estudiante.cedula,
                'edad': estudiante.edad,
                'sexo': estudiante.sexo,
                'nacionalidad': estudiante.nacionalidad,
                'fecha_nacimiento': estudiante.fecha_nacimiento,
                'direccion': estudiante.direccion,
                'correo_electronico': estudiante.correo_electronico,
                'telefono_movil': estudiante.telefono_movil,
                'nivel_educativo': estudiante.nivel_educativo,
                'nombre_emergencia': estudiante.nombre_emergencia,
                'telefono_emergencia': estudiante.telefono_emergencia,
                'tiene_usuario': estudiante.usuarios.exists(),
            })

        return Response(resultados)

    @action(detail=False, methods=['get'], url_path='para-examen')
    def para_examen(self, request):

        user = request.user
        rol = user.rol_nombre

        matriculas = Matricula.objects.select_related(
            'estudiante'
        ).filter(
            estado='matriculado'
        )

        if rol == 'instructor':
            if not user.instructor_id:
                return Response([], status=200)

            matriculas_ids = Calendario.objects.filter(
                instructor_id=user.instructor_id,
                es_examen=False,
                matricula__estado='matriculado'
            ).exclude(
                estado='cancelada'
            ).values_list(
                'matricula_id',
                flat=True
            ).distinct()

            matriculas = matriculas.filter(id__in=matriculas_ids)

        resultados = []

        for matricula in matriculas:

            total_clases = Calendario.objects.filter(
                matricula=matricula,
                es_examen=False,
            ).count()

            if total_clases == 0:
                continue

            clases_completadas = Calendario.objects.filter(
                matricula=matricula,
                es_examen=False,
                estado='completada',
            ).count()

            if clases_completadas < total_clases:
                continue

            tiene_examen = Calendario.objects.filter(
                matricula=matricula,
                es_examen=True,
            ).exists()

            if tiene_examen:
                continue

            resultados.append({
                'id': matricula.id,
                'estudiante_nombre': (
                    f"{matricula.estudiante.nombre} "
                    f"{matricula.estudiante.apellido}"
                ).strip(),
                'estudiante_cedula': matricula.estudiante.cedula,
            })

        return Response(resultados)     
    
    @action(detail=False, methods=['get'], url_path='asignadas-instructor')
    def asignadas_instructor(self, request):
        user = request.user
        rol = user.rol_nombre

        matriculas = Matricula.objects.select_related(
            'estudiante'
        ).filter(
            estado='matriculado'
        )

        if rol == 'instructor':
            if not user.instructor_id:
                return Response([], status=200)

            matriculas_ids = Calendario.objects.filter(
                instructor_id=user.instructor_id,
                es_examen=False
            ).values_list(
                'matricula_id',
                flat=True
            ).distinct()

            matriculas = matriculas.filter(id__in=matriculas_ids)

        resultados = []

        for matricula in matriculas:
            tiene_examen = Calendario.objects.filter(
                matricula=matricula,
                es_examen=True,
            ).exists()

            resultados.append({
                'id': matricula.id,
                'estudiante_nombre': (
                    f"{matricula.estudiante.nombre} "
                    f"{matricula.estudiante.apellido}"
                ).strip(),
                'estudiante_cedula': matricula.estudiante.cedula,
                'tiene_examen': tiene_examen,
            })

        return Response(resultados)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def saldo(request):
    matricula_id = request.query_params.get('matricula')

    if not matricula_id:
        return Response(
            {'error': 'Debe enviar el ID de la matrícula.'},
            status=400
        )

    try:
        matricula = Matricula.objects.select_related('estudiante').get(id=matricula_id)
    except Matricula.DoesNotExist:
        return Response(
            {'error': 'La matrícula no existe.'},
            status=404
        )

    def calcular_monto_total(matricula):
        if matricula.tipo_curso == 'Principiante':
            return Decimal('6500')

        if matricula.tipo_curso == 'Intermedio':
            horas = matricula.horas_reforzamiento or 6
            return Decimal(horas) * Decimal('433.33')

        if matricula.tipo_curso == 'Avanzado':
            horas = matricula.horas_reforzamiento or 2
            return Decimal(horas) * Decimal('433.33')

        return Decimal('0')

    monto_total = calcular_monto_total(matricula)

    total_pagado = Recibo.objects.filter(
        matricula=matricula,
    ).aggregate(
        total=models.Sum('monto_pagado')
    )['total'] or Decimal('0')

    cantidad_pagos = Recibo.objects.filter(matricula=matricula).count()

    saldo_pendiente = monto_total - total_pagado

    return Response({
        'matricula_id': matricula.id,
        'nombre': matricula.estudiante.nombre,
        'apellido': matricula.estudiante.apellido,
        'cedula': matricula.estudiante.cedula,
        'tipo_curso': matricula.tipo_curso,
        'horas_reforzamiento': matricula.horas_reforzamiento,
        'monto_total': float(monto_total),
        'total_pagado': float(total_pagado),
        'saldo_pendiente': float(saldo_pendiente),
        'cantidad_pagos': cantidad_pagos,
        'pagos_permitidos': 2,
    })

class ReciboViewSet(viewsets.ModelViewSet):
    queryset = Recibo.objects.select_related(
        'matricula',
        'matricula__estudiante',
     
    ).all()
    serializer_class = ReciboSerializer
    permission_classes = [IsAuthenticated]

   


class UserViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.select_related(
        'rol',
        'estudiante',
        'instructor',
    ).all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        usuario = self.get_object()
        instructor = usuario.instructor

        self.perform_destroy(usuario)

        if instructor:
            instructor.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='crear-estudiante')
    def crear_usuario_estudiante(self, request):
        matricula_id = request.data.get('matricula_id')

        if not matricula_id:
            return Response(
                {'error': 'Debe enviar la matrícula.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            matricula = Matricula.objects.select_related('estudiante').get(id=matricula_id)
        except Matricula.DoesNotExist:
            return Response(
                {'error': 'Matrícula no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if matricula.estado != 'matriculado':
            return Response(
                {'error': 'No se puede crear usuario porque la matrícula aún no está aprobada.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if matricula.estudiante.usuario:
            return Response(
                {'error': 'Este estudiante ya tiene usuario.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        data.setdefault('first_name', matricula.estudiante.nombre)
        data.setdefault('last_name', matricula.estudiante.apellido)
        data.setdefault('email', matricula.estudiante.correo_electronico)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        matricula.estudiante.usuario = usuario
        matricula.estudiante.save(update_fields=['usuario'])

        return Response(
            self.get_serializer(usuario).data,
            status=status.HTTP_201_CREATED
        )


class CalendarioViewSet(viewsets.ModelViewSet):
    queryset = Calendario.objects.select_related(
        'matricula',
        'matricula__estudiante',
        'matricula__categoria',
        'instructor',
        'modulo',
    ).all()
    serializer_class = CalendarioSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['instructor', 'fecha']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset

        mes = self.request.query_params.get('mes')
        instructor_param = self.request.query_params.get('instructor')

        if mes:
            try:
                anio, m = map(int, mes.split('-'))
                inicio = date(anio, m, 1)
                fin = date(anio + 1, 1, 1) if m == 12 else date(anio, m + 1, 1)
                qs = qs.filter(fecha__gte=inicio, fecha__lt=fin)
            except ValueError:
                pass

        if instructor_param and instructor_param != 'all':
            qs = qs.filter(instructor_id=instructor_param)

        if user.is_superuser or getattr(user, 'rol_nombre', '') == 'admin':
            return qs.order_by('fecha', 'hora_inicio')

        if getattr(user, 'instructor_id', None):
            return qs.filter(instructor_id=user.instructor_id).order_by('fecha', 'hora_inicio')

        if getattr(user, 'estudiante_id', None):
            return qs.filter(matricula__estudiante_id=user.estudiante_id).order_by('fecha', 'hora_inicio')

        return qs.none()

    @action(detail=False, methods=['get'], url_path='hoy')
    def citas_hoy(self, request):
        hoy = date.today()
        citas = self.get_queryset().filter(fecha=hoy)

        serializer = self.get_serializer(citas, many=True)

        return Response({
            'results': serializer.data,
            'count': citas.count(),
            'fecha': hoy.isoformat(),
        })

    @action(detail=False, methods=['post'], url_path='crear-bloque')
    def crear_bloque_citas(self, request):
        serializer = CrearBloqueCitasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        matricula = Matricula.objects.select_related(
            'estudiante',
            'categoria',
        ).get(id=data['matricula_id'])

        instructor = Instructor.objects.get(id=data['instructor_id'])

        rango = obtener_rango_horario(matricula)

        if not rango:
            return Response(
                {'error': 'La matrícula no tiene un horario válido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        horas_por_dia = int(data.get('horas_por_dia', 2))

        if horas_por_dia <= 0:
            return Response(
                {'error': 'Las horas por día deben ser mayores a cero.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        hora_inicio = datetime.strptime(rango[0], '%H:%M').time()

        hora_fin = (
            datetime.combine(date.today(), hora_inicio) +
            timedelta(hours=horas_por_dia)
        ).time()

        if matricula.tipo_curso in ['Intermedio', 'Avanzado']:
            horas_totales = matricula.horas_reforzamiento

            if not horas_totales:
                return Response(
                    {'error': 'La matrícula no tiene horas asignadas para este curso.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            horas_totales = 16

        num_clases = int(horas_totales) // horas_por_dia

        if int(horas_totales) % horas_por_dia != 0:
            num_clases += 1

        fechas = []
        actual = data['fecha_inicio']
        es_extraordinario = str(matricula.modalidad).lower() == 'extraordinario'

        while len(fechas) < num_clases:
            es_fin_semana = actual.weekday() >= 5

            if es_extraordinario and es_fin_semana:
                fechas.append(actual)

            if not es_extraordinario and not es_fin_semana:
                fechas.append(actual)

            actual += timedelta(days=1)

        for fecha_clase in fechas:
            choque = Calendario.objects.filter(
                instructor=instructor,
                fecha=fecha_clase,
                hora_inicio__lt=hora_fin,
                hora_fin__gt=hora_inicio,
                estado__in=['pendiente', 'reprogramada', 'inasistencia']
            ).exists()

            if choque:
                return Response(
                    {
                        'error': (
                            f'El instructor ya tiene ocupado el horario '
                            f'{hora_inicio.strftime("%H:%M")} - {hora_fin.strftime("%H:%M")} '
                            f'el día {fecha_clase}.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        creadas = []

        with transaction.atomic():
            for i, fecha_clase in enumerate(fechas, start=1):
                clase = Calendario.objects.create(
                    matricula=matricula,
                    instructor=instructor,
                    fecha=fecha_clase,
                    hora_inicio=hora_inicio,
                    hora_fin=hora_fin,
                    numero_clase=i,
                    estado='pendiente',
                    es_examen=False,
                )

                creadas.append(clase)

        return Response(
            {
                'message': f'Bloque de {len(creadas)} clases creado correctamente.',
                'fecha_inicio': fechas[0],
                'fecha_fin': fechas[-1],
                'clases_creadas': len(creadas),
                'hora_inicio': hora_inicio.strftime('%H:%M'),
                'hora_fin': hora_fin.strftime('%H:%M'),
                'citas': CalendarioSerializer(creadas, many=True).data,
            },
            status=status.HTTP_201_CREATED
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        aplicar_a = request.data.get('aplicar_a', 'solo')
        instructor_id = request.data.get('instructor')

        if not instructor_id:
            return super().partial_update(request, *args, **kwargs)

        if aplicar_a == 'pendientes':
            clases = Calendario.objects.filter(
                matricula=instance.matricula,
                estado='pendiente',
                es_examen=False,
            )
        else:
            clases = Calendario.objects.filter(id=instance.id)

        for clase in clases:
            choque = Calendario.objects.filter(
                instructor_id=instructor_id,
                fecha=clase.fecha,
                hora_inicio__lt=clase.hora_fin,
                hora_fin__gt=clase.hora_inicio,
                estado__in=['pendiente', 'reprogramada', 'inasistencia']
            ).exclude(id=clase.id).exists()

            if choque:
                return Response(
                    {
                        'error': (
                            f'El instructor ya tiene ocupado el horario '
                            f'{clase.hora_inicio.strftime("%H:%M")} - {clase.hora_fin.strftime("%H:%M")} '
                            f'el día {clase.fecha}.'
                        )
                    },
                    status=400
                )

        clases.update(instructor_id=instructor_id)

        instance.refresh_from_db()
        serializer = self.get_serializer(instance)

        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='crear-examen')
    def crear_examen(self, request):

        user = request.user

        if not user.instructor_id:
            return Response(
                {'error': 'El usuario actual no tiene instructor asignado.'},
                status=400
            )

        matricula_id = request.data.get('matricula_id')
        fecha = request.data.get('fecha')

        hora_inicio = '14:00'
        hora_fin = '16:00'

        try:
            matricula = Matricula.objects.select_related(
                'estudiante'
            ).get(id=matricula_id)

            instructor = Instructor.objects.get(id=user.instructor_id)

        except Matricula.DoesNotExist:
            return Response(
                {'error': 'Matrícula no encontrada.'},
                status=404
            )

        except Instructor.DoesNotExist:
            return Response(
                {'error': 'Instructor no encontrado.'},
                status=404
            )

        if matricula.estado != 'matriculado':
            return Response(
                {
                    'error': (
                        'No se puede programar examen porque '
                        'la matrícula aún no está matriculada.'
                    )
                },
                status=400
            )

        tiene_usuario = matricula.estudiante.usuarios.filter(
            rol__nombre__iexact='estudiante'
        ).exists()

        if not tiene_usuario:
            return Response(
                {
                    'error': (
                        'No se puede programar examen porque '
                        'el estudiante todavía no tiene usuario.'
                    )
                },
                status=400
            )

        total_clases = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False,
        ).count()

        if total_clases == 0:
            return Response(
                {
                    'error': 'El estudiante todavía no tiene clases asignadas.'
                },
                status=400
            )

        clases_completadas = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False,
            estado='completada',
        ).count()

        if clases_completadas < total_clases:
            return Response(
                {
                    'error': (
                        'El estudiante aún no ha completado '
                        'todas sus clases prácticas.'
                    )
                },
                status=400
            )

        examen_existente = Calendario.objects.filter(
            matricula=matricula,
            es_examen=True,
        ).exists()

        if examen_existente:
            return Response(
                {
                    'error': 'Este estudiante ya tiene examen policial asignado.'
                },
                status=400
            )

        examen = Calendario.objects.create(
            matricula=matricula,
            instructor=instructor,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            numero_clase=99,
            estado='pendiente',
            es_examen=True,
        )

        return Response(
            {
                'message': 'Examen policial programado correctamente.',
                'examen': CalendarioSerializer(examen).data,
            },
            status=201
        )


class AsistenciaViewSet(viewsets.ModelViewSet):
    queryset = Asistencia.objects.select_related(
        'clase',
        'clase__matricula',
        'clase__matricula__estudiante',
    ).all()
    serializer_class = AsistenciaSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='marcar')
    def marcar(self, request):
        clase_id = request.data.get('clase_id')
        estado_asistencia = request.data.get('estado')
        observacion = request.data.get('observacion', '')

        if estado_asistencia not in ['asistio', 'falto', 'justificado']:
            return Response(
                {'error': 'Estado de asistencia inválido.'},
                status=400
            )

        try:
            clase = Calendario.objects.get(id=clase_id)
        except Calendario.DoesNotExist:
            return Response(
                {'error': 'Clase no encontrada.'},
                status=404
            )

        asistencia, created = Asistencia.objects.update_or_create(
            clase=clase,
            defaults={
                'estado': estado_asistencia,
                'observacion': observacion,
            }
        )

        return Response(AsistenciaSerializer(asistencia).data)

    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        matriculas = Matricula.objects.select_related('estudiante', 'plan_estudio').all()
        resultado = []

        for matricula in matriculas:
            clases = Calendario.objects.filter(matricula=matricula).order_by('numero_clase')
            asistencias = Asistencia.objects.filter(clase__matricula=matricula)

            total_marcadas = asistencias.exclude(estado='justificado').count()
            presentes = asistencias.filter(estado='asistio').count()

            porcentaje = round((presentes / total_marcadas) * 100) if total_marcadas > 0 else 0

            resultado.append({
                'matricula_id': matricula.id,
                'nombre': matricula.estudiante.nombre,
                'apellido': matricula.estudiante.apellido,
                'cedula': matricula.estudiante.cedula,
                'plan_estudio': matricula.plan_estudio.nombre,
                'tipo_curso': matricula.plan_estudio.tipo_curso,
                'total_clases': clases.count(),
                'porcentaje': porcentaje,
            })

        return Response(resultado)




class NotasViewSet(viewsets.ModelViewSet):
    queryset = Notas.objects.select_related(
        'matricula',
        'matricula__estudiante',
        'instructor',
        'plan_de_estudio',
    ).all()
    serializer_class = NotasSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = Notas.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'instructor',
            'plan_de_estudio',
        ).all()

        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol in ['admin', 'administrador']:
            return queryset

        if rol == 'instructor' and user.instructor_id:
            return queryset.filter(instructor_id=user.instructor_id)

        if rol == 'estudiante' and user.estudiante_id:
            return queryset.filter(matricula__estudiante_id=user.estudiante_id)

        return queryset.none()

    def create(self, request, *args, **kwargs):
        """Crear nota práctica asignando instructor y plan_de_estudio automáticamente"""

        if not request.user.instructor:
            return Response({
                'error': 'El usuario actual no tiene instructor asignado.'
            }, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()

        matricula_id = data.get('matricula')
        if not matricula_id:
            return Response({
                'error': 'Debe seleccionar una matrícula.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            matricula = Matricula.objects.get(id=matricula_id)
        except Matricula.DoesNotExist:
            return Response({
                'error': 'Matrícula no encontrada.'
            }, status=status.HTTP_404_NOT_FOUND)

        if Notas.objects.filter(
            matricula=matricula,
            tipo_nota='practico'
        ).exists():
            return Response({
                'error': 'Ya existe una nota práctica registrada para este estudiante.'
            }, status=status.HTTP_400_BAD_REQUEST)

        progresos = ProgresoTema.objects.filter(matricula=matricula)
        total_temas = progresos.count()

        if total_temas == 0:
            return Response({
                'error': 'El estudiante no tiene temas asignados en su plan de estudio.'
            }, status=status.HTTP_400_BAD_REQUEST)

        completados = progresos.filter(
            estudiante_completado=True,
            instructor_completado=True
        ).count()

        plan_completado = completados == total_temas

        if not plan_completado:
            return Response({
                'error': f'No se puede registrar la nota porque el estudiante no ha completado el plan de estudio. Progreso: {completados}/{total_temas} temas completados.'
            }, status=status.HTTP_400_BAD_REQUEST)

        plan_estudio = matricula.plan_de_estudio

        if not plan_estudio:
            return Response({
                'error': 'La matrícula no tiene un plan de estudio asignado.'
            }, status=status.HTTP_400_BAD_REQUEST)

        data['instructor'] = request.user.instructor.id
        data['plan_de_estudio'] = plan_estudio.id
        data['tipo_nota'] = 'practico'

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        nota = serializer.save()

        # OJO:
        # Si todavía falta examen teórico, NO conviene finalizar aquí.
        # Solo finaliza si ya existe una nota teórica aprobada.
        nota_teorica_aprobada = Notas.objects.filter(
            matricula=matricula,
            tipo_nota='teorico',
            nota__gte=80
        ).exists()

        if nota_teorica_aprobada:
            matricula.estado = 'finalizado'
            matricula.save(update_fields=['estado'])

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)

    if not user:
        return Response({
            'error': 'Credenciales inválidas'
        }, status=401)

    token, created = Token.objects.get_or_create(user=user)

    return Response({
        'token': token.key,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'rol': user.rol.nombre if user.rol else 'sin rol',
        }
    })


from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta
from decimal import Decimal

class DashboardGananciasView(APIView):
    """Endpoint para obtener ganancias mensuales y matriculados"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            hoy = datetime.now().date()
            
            # Generar últimos 6 meses (desde hace 5 meses hasta el actual)
            meses_resultado = []
            fechas_meses = []
            
            for i in range(5, -1, -1):
                # Calcular fecha del mes
                if i == 0:
                    fecha_mes = hoy.replace(day=1)
                else:
                    mes_anterior = hoy.month - i
                    año_anterior = hoy.year
                    if mes_anterior <= 0:
                        mes_anterior += 12
                        año_anterior -= 1
                    fecha_mes = datetime(año_anterior, mes_anterior, 1).date()
                
                mes_str = fecha_mes.strftime('%Y-%m')
                fechas_meses.append({
                    'fecha': fecha_mes,
                    'mes_str': mes_str,
                    'nombre_mes': self._get_nombre_mes(fecha_mes.month)
                })
            
            # Para cada mes, calcular ganancias y matriculados
            for fecha_info in fechas_meses:
                fecha_mes = fecha_info['fecha']
                # Calcular fin del mes
                if fecha_mes.month == 12:
                    fecha_fin = datetime(fecha_mes.year + 1, 1, 1).date()
                else:
                    fecha_fin = datetime(fecha_mes.year, fecha_mes.month + 1, 1).date()
                
                # Ganancias del mes
                total_ganancias = Recibo.objects.filter(
                    fecha_pago__year=fecha_mes.year,
                    fecha_pago__month=fecha_mes.month,
                    tipo_pago__in=['completo', 'anticipo']
                ).aggregate(total=Sum('monto_pagado'))['total'] or Decimal('0')
                
                # Matriculados del mes
                total_matriculados = Recibo.objects.filter(
                    fecha_pago__year=fecha_mes.year,
                    fecha_pago__month=fecha_mes.month,
                    tipo_pago__in=['completo', 'beneficio']
                ).values('matricula').distinct().count()
                
                if total_ganancias > 0 or total_matriculados > 0:
                    meses_resultado.append({
                        'mes': fecha_info['mes_str'],
                        'total': float(total_ganancias),
                        'matriculados': total_matriculados
                    })
            
            return Response(meses_resultado)
            
        except Exception as e:
            print(f"Error en DashboardGananciasView: {str(e)}")
            import traceback
            traceback.print_exc()
            # Retornar error detallado para depuración
            return Response(
                {'error': str(e), 'tipo': type(e).__name__},
                status=500
            )
    
    def _get_nombre_mes(self, mes_numero):
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        return meses.get(mes_numero, "")
        



class DashboardResumenView(APIView):
    """Endpoint para resumen del dashboard"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            hoy = datetime.now().date()
            
            # Total de matriculados (todas las matrículas activas)
            total_matriculados = Matricula.objects.filter(
                estado='matriculado'
            ).count()
            
            # Estudiantes activos (mismo que matriculados para este caso)
            estudiantes_activos = Estudiante.objects.filter(
                activo=True
            ).count()
            
            # Egresados del mes actual
            egresados_mes = Matricula.objects.filter(
                estado='finalizado',
                fecha_registro__year=hoy.year,
                fecha_registro__month=hoy.month
            ).count()
            
            # Ingresos del mes actual
            ingresos_mes = Recibo.objects.filter(
                fecha_pago__year=hoy.year,
                fecha_pago__month=hoy.month,
                tipo_pago__in=['completo', 'anticipo']
            ).aggregate(total=Sum('monto_pagado'))['total'] or Decimal('0')
            
            # Ingresos totales históricos
            ingresos_totales = Recibo.objects.filter(
                tipo_pago__in=['completo', 'anticipo']
            ).aggregate(total=Sum('monto_pagado'))['total'] or Decimal('0')
            
            return Response({
                'total_matriculados': total_matriculados,
                'estudiantes_activos': estudiantes_activos,
                'egresados_mes': egresados_mes,
                'ingresos_mes': float(ingresos_mes),
                'ingresos_totales': float(ingresos_totales),
            })
            
        except Exception as e:
            print(f"Error en DashboardResumenView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {
                    'total_matriculados': 0,
                    'estudiantes_activos': 0,
                    'egresados_mes': 0,
                    'ingresos_mes': 0,
                    'ingresos_totales': 0,
                    'error': str(e)
                },
                status=200  # Cambiado a 200 para que el frontend no falle
            )



class DashboardIngresosMensualesView(APIView):
    """Endpoint específico para ingresos mensuales (últimos 6 meses)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            hoy = datetime.now().date()
            fecha_limite = hoy - timedelta(days=180)
            
            # Agrupar recibos por mes
            ingresos = Recibo.objects.filter(
                fecha_pago__gte=fecha_limite,
                tipo_pago__in=['completo', 'anticipo']
            ).annotate(
                mes=TruncMonth('fecha_pago')
            ).values('mes').annotate(
                total=Sum('monto_pagado')
            ).order_by('mes')
            
            # Generar últimos 6 meses
            meses_resultado = []
            for i in range(5, -1, -1):
                fecha_mes = hoy.replace(day=1) - timedelta(days=30*i)
                mes_str = fecha_mes.strftime('%Y-%m')
                
                # Buscar si hay datos para este mes
                total = 0
                for ingreso in ingresos:
                    if ingreso['mes'] and ingreso['mes'].strftime('%Y-%m') == mes_str:
                        total = float(ingreso['total'])
                        break
                
                meses_resultado.append({
                    'mes': mes_str,
                    'total': total,
                    'nombre_mes': self._get_nombre_mes(fecha_mes.month)
                })
            
            return Response(meses_resultado)
            
        except Exception as e:
            print(f"Error en DashboardIngresosMensualesView: {e}")
            # Datos de ejemplo para desarrollo
            return Response([
                {"mes": "2025-01", "total": 12500, "nombre_mes": "Enero"},
                {"mes": "2025-02", "total": 18900, "nombre_mes": "Febrero"},
                {"mes": "2025-03", "total": 15200, "nombre_mes": "Marzo"},
                {"mes": "2025-04", "total": 22400, "nombre_mes": "Abril"},
                {"mes": "2025-05", "total": 19800, "nombre_mes": "Mayo"},
                {"mes": "2025-06", "total": 21000, "nombre_mes": "Junio"},
            ])
    
    def _get_nombre_mes(self, mes_numero):
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        return meses.get(mes_numero, "")

# views.py

from django.utils import timezone
from ..models import ProgresoTema, Notificacion, HistorialPlanEstudio

class ProgresoTemaViewSet(viewsets.ModelViewSet):
    queryset = ProgresoTema.objects.select_related(
        'matricula',
        'matricula__estudiante',
        'tema',
        'tema__plan_estudio'
    ).prefetch_related(
        'tema__subtemas'
    ).all()

    serializer_class = ProgresoTemaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        queryset = self.queryset

        if rol in ['admin', 'administrador'] or user.is_staff or user.is_superuser:
            return queryset.order_by(
                'matricula_id',
                'tema__orden',
                'id'
            )

        if rol == 'estudiante' and hasattr(user, 'estudiante') and user.estudiante:
            return queryset.filter(
                matricula__estudiante=user.estudiante
            ).order_by(
                '-matricula__fecha_registro',
                'tema__orden',
                'id'
            )

        if rol == 'instructor' and hasattr(user, 'instructor') and user.instructor:
            return queryset.filter(
                matricula__clases__instructor=user.instructor
            ).distinct().order_by(
                'matricula_id',
                'tema__orden',
                'id'
            )

        return ProgresoTema.objects.none()

    def _actualizar_progreso(self, progreso):
        progreso.completado = (
            progreso.estudiante_completado and
            progreso.instructor_completado
        )

        progreso.save()

        if progreso.completado:
            self._desbloquear_siguiente(progreso)

    def _desbloquear_siguiente(self, progreso_actual):
        progresos = list(
            ProgresoTema.objects.filter(
                matricula=progreso_actual.matricula
            ).select_related(
                'tema'
            ).order_by(
                'tema__orden',
                'id'
            )
        )

        for index, progreso in enumerate(progresos):
            if progreso.id == progreso_actual.id:
                if index + 1 < len(progresos):
                    siguiente = progresos[index + 1]

                    if not siguiente.desbloqueado:
                        siguiente.desbloqueado = True
                        siguiente.save()

                        usuario_estudiante = progreso_actual.matricula.estudiante.usuarios.first()

                        if usuario_estudiante:
                            try:
                                Notificacion.objects.create(
                                    estudiante=usuario_estudiante,
                                    tema=siguiente.tema,
                                    tipo='tema_desbloqueado',
                                    mensaje=(
                                        f"Nuevo tema desbloqueado: "
                                        f"'{siguiente.tema.titulo}'."
                                    ),
                                    leida=False
                                )
                            except Exception as e:
                                print(f"Error creando notificación: {e}")

                break

    @action(detail=True, methods=['post'], url_path='marcar-estudiante')
    def marcar_estudiante(self, request, pk=None):
        try:
            progreso = self.get_object()

            if not progreso.desbloqueado:
                return Response({
                    'success': False,
                    'error': 'Este tema aún no está disponible. Completa el tema anterior primero.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if progreso.estudiante_completado:
                return Response({
                    'success': False,
                    'error': 'Ya habías marcado este tema como recibido'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                progreso.estudiante_completado = True
                progreso.fecha_estudiante = timezone.now()

                self._actualizar_progreso(progreso)

                if progreso.instructor_completado:
                    mensaje = "Tema completado. El siguiente tema fue desbloqueado."
                else:
                    mensaje = "Tema marcado como recibido. Falta confirmación del instructor."

            serializer = self.get_serializer(progreso)

            return Response({
                'success': True,
                'message': mensaje,
                'data': serializer.data
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='marcar-instructor')
    def marcar_instructor(self, request, pk=None):
        try:
            progreso = self.get_object()

            if not progreso.desbloqueado:
                return Response({
                    'success': False,
                    'error': 'Este tema aún no está disponible. Completa el tema anterior primero.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if progreso.instructor_completado:
                return Response({
                    'success': False,
                    'error': 'Ya habías marcado este tema como dado'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                progreso.instructor_completado = True
                progreso.fecha_instructor = timezone.now()

                self._actualizar_progreso(progreso)

                if progreso.estudiante_completado:
                    mensaje = "Tema completado. El siguiente tema fue desbloqueado."
                else:
                    mensaje = "Tema marcado como dado. Falta confirmación del estudiante."

            serializer = self.get_serializer(progreso)

            return Response({
                'success': True,
                'message': mensaje,
                'data': serializer.data
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='admin-forzar')
    def admin_forzar(self, request, pk=None):
        rol = str(getattr(request.user, 'rol', '')).lower()

        if (
            rol != 'admin'
            and rol != 'administrador'
            and not request.user.is_staff
            and not request.user.is_superuser
        ):
            return Response({
                'success': False,
                'error': 'Solo administradores pueden realizar esta acción'
            }, status=status.HTTP_403_FORBIDDEN)

        progreso = self.get_object()
        tipo_check = request.data.get('tipo')
        valor = request.data.get('valor')

        if isinstance(valor, str):
            valor = valor.lower() == 'true'

        if tipo_check not in ['estudiante', 'instructor']:
            return Response({
                'success': False,
                'error': 'Tipo de check inválido. Use "estudiante" o "instructor"'
            }, status=status.HTTP_400_BAD_REQUEST)

        if valor not in [True, False]:
            return Response({
                'success': False,
                'error': 'Valor inválido. Use true o false'
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            old_estudiante = progreso.estudiante_completado
            old_instructor = progreso.instructor_completado

            if tipo_check == 'estudiante':
                progreso.estudiante_completado = valor
            else:
                progreso.instructor_completado = valor

            progreso.fecha_admin_edit = timezone.now()

            self._actualizar_progreso(progreso)

            try:
                HistorialPlanEstudio.objects.create(
                    progreso_tema=progreso,
                    usuario=request.user,
                    accion='admin_forzar',
                    valor_anterior_estudiante=old_estudiante,
                    valor_anterior_instructor=old_instructor,
                    valor_nuevo_estudiante=progreso.estudiante_completado,
                    valor_nuevo_instructor=progreso.instructor_completado
                )
            except Exception as e:
                print(f"Error al guardar historial: {e}")

            check_nombre = "estudiante" if tipo_check == 'estudiante' else "instructor"
            accion_texto = "habilitado" if valor else "deshabilitado"

            usuario_estudiante = progreso.matricula.estudiante.usuarios.first()

            if usuario_estudiante:
                try:
                    Notificacion.objects.create(
                        estudiante=usuario_estudiante,
                        tema=progreso.tema,
                        tipo='intervencion_admin',
                        mensaje=(
                            f"El administrador {request.user.username} ha {accion_texto} "
                            f"el check de {check_nombre} para el tema "
                            f"'{progreso.tema.titulo}'."
                        ),
                        leida=False
                    )
                except Exception as e:
                    print(f"Error creando notificación: {e}")

        serializer = self.get_serializer(progreso)

        return Response({
            'success': True,
            'message': f'Check de {check_nombre} actualizado exitosamente',
            'data': serializer.data
        })

    @action(detail=False, methods=['get'], url_path='verificar-plan-completado')
    def verificar_plan_completado(self, request):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        resultado = []

        if rol in ['admin', 'administrador'] or user.is_staff or user.is_superuser:
            matriculas = Matricula.objects.filter(estado='matriculado')

        elif hasattr(user, 'instructor') and user.instructor:
            matriculas = Matricula.objects.filter(
                clases__instructor=user.instructor,
                estado='matriculado'
            ).distinct()

        elif hasattr(user, 'estudiante') and user.estudiante:
            matriculas = Matricula.objects.filter(
                estudiante=user.estudiante,
                estado='matriculado'
            )

        else:
            return Response({
                'success': False,
                'error': 'Usuario no tiene permisos para acceder a esta información'
            }, status=status.HTTP_403_FORBIDDEN)

        for matricula in matriculas:
            if not matricula.plan_de_estudio:
                continue

            progresos = ProgresoTema.objects.filter(matricula=matricula)

            total_temas = progresos.count()

            if total_temas == 0:
                continue

            completados = progresos.filter(
                estudiante_completado=True,
                instructor_completado=True
            ).count()

            plan_completado = completados == total_temas
            porcentaje = round((completados / total_temas * 100))

            if plan_completado:
                resultado.append({
                    'matricula_id': matricula.id,
                    'plan_nombre': matricula.plan_de_estudio.nombre if matricula.plan_de_estudio else 'Sin plan',
                    'tipo_curso': matricula.tipo_curso,
                    'total_temas': total_temas,
                    'temas_completados': completados,
                    'porcentaje': porcentaje,
                    'plan_completado': plan_completado,
                    'puede_presentar_examen': plan_completado,
                    'estudiante_nombre': f"{matricula.estudiante.nombre} {matricula.estudiante.apellido}",
                    'estudiante_cedula': matricula.estudiante.cedula,
                    'estudiante_id': matricula.estudiante.id,
                    'fecha_inscripcion': matricula.fecha_registro,
                })

        return Response(resultado)

    @action(detail=True, methods=['get'], url_path='plan-completado')
    def plan_completado(self, request, pk=None):
        try:
            matricula = Matricula.objects.get(id=pk)

            progresos = ProgresoTema.objects.filter(matricula=matricula)

            total_temas = progresos.count()

            if total_temas == 0:
                return Response({
                    'success': True,
                    'matricula_id': matricula.id,
                    'plan_completado': False,
                    'total_temas': 0,
                    'temas_completados': 0,
                    'porcentaje': 0,
                    'mensaje': 'No hay temas asignados para este plan'
                })

            completados = progresos.filter(
                estudiante_completado=True,
                instructor_completado=True
            ).count()

            plan_completado = completados == total_temas
            porcentaje = round((completados / total_temas * 100))

            return Response({
                'success': True,
                'matricula_id': matricula.id,
                'plan_completado': plan_completado,
                'total_temas': total_temas,
                'temas_completados': completados,
                'porcentaje': porcentaje
            })

        except Matricula.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Matrícula no encontrada'
            }, status=status.HTTP_404_NOT_FOUND)


class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para notificaciones del administrador"""
    
    queryset = Notificacion.objects.all()  # ← NECESARIO
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notificacion.objects.all().order_by('-fecha_creacion')
    
    @action(detail=True, methods=['post'], url_path='marcar-leida')
    def marcar_leida(self, request, pk=None):
        notificacion = self.get_object()
        notificacion.leida = True
        notificacion.save()
        return Response({'success': True, 'message': 'Notificación marcada como leída'})


class DashboardPlanViewSet(viewsets.ViewSet):
    """ViewSet para el dashboard con estadísticas"""
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='estudiante-progreso')
    def estudiante_progreso(self, request):
        user = request.user

        if not user.estudiante:
            return Response([])

        progresos = ProgresoTema.objects.filter(
            matricula__estudiante=user.estudiante
        ).select_related(
            'matricula',
            'subtema',
            'subtema__tema',
            'subtema__tema__plan_estudio'
        ).order_by(
            'subtema__tema__orden',
            'subtema__orden'
        )

        return Response(ProgresoTemaSerializer(progresos, many=True).data)
    
    @action(detail=False, methods=['get'], url_path='instructor-vista')
    def instructor_vista(self, request):
        """Vista para instructores: ver estudiantes y su progreso"""
        # Verificar que sea instructor
        # if not request.user.groups.filter(name='Instructores').exists():
        #     return Response({'error': 'No autorizado'}, status=403)
        
        # Obtener todos los estudiantes (o filtrados por curso)
        estudiantes = Usuario.objects.filter(groups__name='Estudiantes')
        
        resultado = []
        for estudiante in estudiantes:
            progreso_estudiante = []
            planes = PlanEstudio.objects.filter(activo=True)
            
            for plan in planes:
                temas = plan.temas.all()
                progresos = ProgresoTema.objects.filter(
                    estudiante=estudiante,
                    tema__in=temas
                )
                
                total = temas.count()
                completados = progresos.filter(
                    instructor_completado=True  # Instructor solo ve su check
                ).count()
                
                progreso_estudiante.append({
                    'plan_id': plan.id,
                    'plan_nombre': plan.nombre,
                    'progreso_instructor': round((completados / total * 100) if total > 0 else 0),
                    'total_temas': total,
                    'clases_dadas': completados
                })
            
            resultado.append({
                'estudiante_id': estudiante.id,
                'estudiante_nombre': estudiante.username,
                'progreso_general': progreso_estudiante
            })
        
        return Response(resultado)
    
    @action(detail=False, methods=['get'], url_path='admin-vista')
    def admin_vista(self, request):
        """Vista para administradores: ver todo el sistema"""
        if not request.user.is_staff:
            return Response({'error': 'No autorizado'}, status=403)
        
        # Estadísticas generales
        total_estudiantes = Usuario.objects.filter(groups__name='Estudiantes').count()
        total_planes = PlanEstudio.objects.count()
        
        # Temas bloqueados (donde falta un check)
        temas_bloqueados = ProgresoTema.objects.filter(
            Q(estudiante_completado=False) | Q(instructor_completado=False)
        ).exclude(
            estudiante_completado=True, instructor_completado=True
        )
        
        # Notificaciones no leídas
        notificaciones_no_leidas = Notificacion.objects.filter(leida=False).count()
        
        # Progreso general
        todos_progresos = ProgresoTema.objects.all()
        total_temas_progreso = todos_progresos.count()
        completados_total = todos_progresos.filter(
            estudiante_completado=True, instructor_completado=True
        ).count()
        
        return Response({
            'estadisticas': {
                'total_estudiantes': total_estudiantes,
                'total_planes': total_planes,
                'temas_bloqueados': temas_bloqueados.count(),
                'notificaciones_pendientes': notificaciones_no_leidas,
                'tasa_completacion': round((completados_total / total_temas_progreso * 100) if total_temas_progreso > 0 else 0)
            },
            'temas_bloqueados_detalle': ProgresoTemaSerializer(temas_bloqueados[:10], many=True).data,
            'notificaciones_recientes': NotificacionSerializer(
                Notificacion.objects.filter(leida=False)[:10], 
                many=True
            ).data
        })
    

class PreguntaExamenTeoricoViewSet(viewsets.ModelViewSet):
    queryset = PreguntaExamenTeorico.objects.prefetch_related('opciones').all()
    serializer_class = PreguntaExamenTeoricoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        queryset = PreguntaExamenTeorico.objects.prefetch_related(
            'opciones'
        ).all().order_by('-fecha_creacion')

        # tipo_curso = self.request.query_params.get('tipo_curso')
        activa = self.request.query_params.get('activa')

        # if tipo_curso:
        #     queryset = queryset.filter(tipo_curso=tipo_curso)

        if activa is not None:
            if activa.lower() == 'true':
                queryset = queryset.filter(activa=True)
            elif activa.lower() == 'false':
                queryset = queryset.filter(activa=False)

        if rol in ['admin', 'administrador']:
            return queryset

        return queryset.none()

    def perform_create(self, serializer):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol not in ['admin', 'administrador']:
            raise serializers.ValidationError(
                'Solo el administrador puede crear preguntas del examen teórico.'
            )

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol not in ['admin', 'administrador']:
            raise serializers.ValidationError(
                'Solo el administrador puede editar preguntas del examen teórico.'
            )

        serializer.save()

    def destroy(self, request, *args, **kwargs):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol not in ['admin', 'administrador']:
            return Response(
                {'error': 'Solo el administrador puede eliminar preguntas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)
    
class ExamenTeoricoViewSet(viewsets.ModelViewSet):
    queryset = ExamenTeorico.objects.select_related(
        'matricula',
        'matricula__estudiante',
        'habilitado_por',
    ).all()

    serializer_class = ExamenTeoricoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        queryset = ExamenTeorico.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'habilitado_por',
        ).all().order_by('-id')

        if rol in ['admin', 'administrador']:
            return queryset

        if rol == 'instructor' and user.instructor_id:
            return queryset.filter(habilitado_por_id=user.instructor_id)

        if rol == 'estudiante' and user.estudiante_id:
            return queryset.filter(matricula__estudiante_id=user.estudiante_id)

        return queryset.none()

    def create(self, request, *args, **kwargs):
        return Response(
            {'error': 'Para habilitar un examen usa /api/examen-teorico/habilitar/.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=False, methods=['post'], url_path='habilitar')
    def habilitar(self, request):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol != 'instructor' or not user.instructor_id:
            return Response(
                {'error': 'Solo un instructor puede habilitar el examen teórico.'},
                status=status.HTTP_403_FORBIDDEN
            )

        matricula_id = request.data.get('matricula_id')

        if not matricula_id:
            return Response(
                {'error': 'Debe enviar la matrícula del estudiante.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            matricula = Matricula.objects.select_related(
                'estudiante',
                'plan_de_estudio',
            ).get(id=matricula_id)
        except Matricula.DoesNotExist:
            return Response(
                {'error': 'Matrícula no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if matricula.estado not in ['matriculado', 'finalizado']:
            return Response(
                {
                    'error': (
                        'El estudiante debe estar matriculado o tener el plan finalizado '
                        'para habilitar el examen.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        tiene_clase_con_instructor = Calendario.objects.filter(
            matricula=matricula,
            instructor_id=user.instructor_id,
            es_examen=False,
        ).exists()

        if not tiene_clase_con_instructor:
            return Response(
                {'error': 'Este estudiante no está asignado a este instructor.'},
                status=status.HTTP_403_FORBIDDEN
            )

        progresos = ProgresoTema.objects.filter(matricula=matricula)

        total_temas = progresos.count()

        if total_temas == 0:
            return Response(
                {'error': 'El estudiante no tiene temas asignados en su plan de estudio.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        completados = progresos.filter(
            estudiante_completado=True,
            instructor_completado=True,
        ).count()

        if completados < total_temas:
            return Response(
                {
                    'error': (
                        f'No se puede habilitar el examen porque el plan de estudio '
                        f'aún no está completo. Progreso: {completados}/{total_temas}.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        preguntas_disponibles = PreguntaExamenTeorico.objects.filter(
                activa=True,
            ).count()

        if preguntas_disponibles == 0:
            return Response(
                {
                    'error': (
                        f'No existen preguntas activas para el examen teórico. '
                        f'{matricula.tipo_curso}.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        examen, created = ExamenTeorico.objects.get_or_create(
            matricula=matricula,
            defaults={
                'habilitado_por_id': user.instructor_id,
                'estado': 'habilitado',
                'fecha_habilitado': timezone.now(),
            }
        )

        if not created:

                if examen.estado == 'realizado' and examen.nota is not None and examen.nota >= 80:
                    return Response(
                        {'error': 'El estudiante ya aprobó el examen teórico.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if examen.estado == 'realizado' and examen.nota is not None and examen.nota < 80:
                    RespuestaExamenTeorico.objects.filter(examen=examen).delete()

                    examen.estado = 'habilitado'
                    examen.nota = None
                    examen.fecha_realizado = None
                    examen.fecha_habilitado = timezone.now()
                    examen.habilitado_por_id = user.instructor_id

                    examen.save(update_fields=[
                        'estado',
                        'nota',
                        'fecha_realizado',
                        'fecha_habilitado',
                        'habilitado_por',
                    ])

                else:
                    examen.estado = 'habilitado'
                    examen.fecha_habilitado = timezone.now()
                    examen.habilitado_por_id = user.instructor_id

                    examen.save(update_fields=[
                        'estado',
                        'fecha_habilitado',
                        'habilitado_por',
                    ])

        serializer = self.get_serializer(examen)

        return Response(
                {
                    'message': 'Examen teórico habilitado correctamente.',
                    'examen': serializer.data,
                },
                status=status.HTTP_200_OK
            )

    @action(detail=False, methods=['get'], url_path='mi-examen')
    def mi_examen(self, request):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""


        print("ROL:", rol)
        print("USER:", user.username)
        print("ESTUDIANTE ID:", user.estudiante_id)

        if rol != 'estudiante' or not user.estudiante_id:
            
            return Response(
                {'error': 'Solo el estudiante puede consultar su examen teórico.'},
                status=status.HTTP_403_FORBIDDEN
            )

        examen = ExamenTeorico.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'habilitado_por',
        ).filter(
            matricula__estudiante_id=user.estudiante_id
        ).first()

        if not examen:
            return Response(
                {
                    'disponible': False,
                    'message': 'Todavía no tienes examen teórico habilitado.',
                },
                status=status.HTTP_200_OK
            )

        if examen.estado == 'realizado':
            return Response(
                {
                    'disponible': False,
                    'realizado': True,
                    'message': 'Ya realizaste el examen teórico.',
                    'examen': self.get_serializer(examen).data,
                },
                status=status.HTTP_200_OK
            )

        if examen.estado != 'habilitado':
            return Response(
                {
                    'disponible': False,
                    'message': 'Tu examen teórico todavía no está disponible.',
                },
                status=status.HTTP_200_OK
            )

        preguntas = PreguntaExamenTeorico.objects.prefetch_related(
            'opciones'
        ).filter(
            activa=True,
        ).order_by('id')

        preguntas_serializer = PreguntaExamenEstudianteSerializer(
            preguntas,
            many=True
        )

        return Response(
            {
                'disponible': True,
                'realizado': False,
                'examen': self.get_serializer(examen).data,
                'preguntas': preguntas_serializer.data,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], url_path='enviar')
    def enviar(self, request, pk=None):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol != 'estudiante' or not user.estudiante_id:
            return Response(
                {'error': 'Solo el estudiante puede enviar el examen teórico.'},
                status=status.HTTP_403_FORBIDDEN
            )

        examen = self.get_object()

        if examen.matricula.estudiante_id != user.estudiante_id:
            return Response(
                {'error': 'No puedes enviar un examen que no te pertenece.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if examen.estado != 'habilitado':
            return Response(
                {'error': 'Este examen no está habilitado o ya fue realizado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RespuestaEnviarExamenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        respuestas = serializer.validated_data['respuestas']

        preguntas = PreguntaExamenTeorico.objects.prefetch_related(
            'opciones'
        ).filter(
            activa=True,
        )

        total_preguntas = preguntas.count()

        if total_preguntas == 0:
            return Response(
                {'error': 'No hay preguntas activas para este examen.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        preguntas_ids = set(preguntas.values_list('id', flat=True))
        respuestas_ids = set(
            int(respuesta['pregunta_id'])
            for respuesta in respuestas
        )

        if preguntas_ids != respuestas_ids:
            return Response(
                {
                    'error': (
                        'Debe responder todas las preguntas del examen '
                        'antes de enviarlo.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            RespuestaExamenTeorico.objects.filter(examen=examen).delete()

            correctas = 0

            for respuesta in respuestas:
                pregunta_id = respuesta['pregunta_id']
                opcion_id = respuesta['opcion_id']

                try:
                    pregunta = preguntas.get(id=pregunta_id)
                except PreguntaExamenTeorico.DoesNotExist:
                    return Response(
                        {'error': 'Una de las preguntas no pertenece a este examen.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    opcion = OpcionPreguntaExamenTeorico.objects.get(
                        id=opcion_id,
                        pregunta=pregunta,
                    )
                except OpcionPreguntaExamenTeorico.DoesNotExist:
                    return Response(
                        {'error': 'Una de las opciones no pertenece a la pregunta indicada.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                es_correcta = opcion.es_correcta

                print("PREGUNTA:", pregunta.id, pregunta.texto)
                print("OPCION SELECCIONADA:", opcion.id, opcion.texto)
                print("ES CORRECTA:", opcion.es_correcta)

                if es_correcta:
                    correctas += 1
                RespuestaExamenTeorico.objects.create(
                    examen=examen,
                    pregunta=pregunta,
                    opcion_seleccionada=opcion,
                    correcta=es_correcta,
                )
            nota_final = round((correctas / total_preguntas) * 100, 2)
            examen.estado = 'realizado'
            examen.nota = nota_final
            examen.fecha_realizado = timezone.now()
            examen.save(
                update_fields=[
                    'estado',
                    'nota',
                    'fecha_realizado',
                ]
            )

            plan = examen.matricula.plan_de_estudio

            if not plan:
                return Response(
                    {'error': 'La matrícula no tiene plan de estudio asignado.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            instructor = examen.habilitado_por

            if not instructor:
                return Response(
                    {'error': 'El examen no tiene instructor asignado.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            Notas.objects.update_or_create(
                matricula=examen.matricula,
                tipo_nota='teorico',
                defaults={
                    'instructor': instructor,
                    'plan_de_estudio': plan,
                    'nota': str(nota_final),
                    'comentario': (
                        'Examen teórico aprobado automáticamente por el sistema.'
                        if nota_final >= 80
                        else 'Examen teórico reprobado. Puede ser habilitado nuevamente por el instructor.'
                    ),
                }
            )

        return Response(
            {
                'message': 'Examen enviado y calificado correctamente.',
                'total_preguntas': total_preguntas,
                'correctas': correctas,
                'nota': nota_final,
                'resultado': 'Aprobado' if nota_final >= 80 else 'Reprobado',
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get'], url_path='respuestas')
    def respuestas(self, request, pk=None):
        examen = self.get_object()

        respuestas = RespuestaExamenTeorico.objects.select_related(
            'pregunta',
            'opcion_seleccionada',
        ).filter(
            examen=examen
        )

        serializer = RespuestaExamenTeoricoSerializer(respuestas, many=True)

        return Response(serializer.data)
    

class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get_foto_url(self, request, instructor):
        foto = getattr(instructor, 'foto', None)

        if foto:
            try:
                return request.build_absolute_uri(foto.url)
            except Exception:
                return None

        return None

    def serializar_instructor(self, request, instructor):
        return {
            "id": instructor.id,
            "nombre": instructor.nombre,
            "apellido": instructor.apellido,
            "telefono": instructor.numero_telefono,
            "direccion": instructor.direccion,
            "edad": instructor.edad,
            "experiencia": instructor.experiencia,
            "categoria": instructor.categoria_instructor if instructor.categoria_instructor else None,
            "foto": self.get_foto_url(request, instructor),
            "cedula": instructor.cedula or "",
            "nacionalidad": instructor.nacionalidad or "",
            "nivel_escolar": instructor.nivel_escolar or "",
            "antecedentes_penales": instructor.antecedentes_penales or "",
            "centro_trabajo": instructor.centro_trabajo or "",
            "cargo": instructor.cargo or "",
            "curso_aprobado_instructor": instructor.curso_aprobado_instructor or "",
            "fecha_ingreso": instructor.fecha_ingreso.isoformat() if instructor.fecha_ingreso else "",
            "fecha_salida": instructor.fecha_salida.isoformat() if instructor.fecha_salida else "",
            "motivo_salida": instructor.motivo_salida or "",
            "infracciones_resoluciones": instructor.infracciones_resoluciones or "",
        }

    def serializar_estudiante(self, estudiante):
        return {
            "id": estudiante.id,
            "nombre": estudiante.nombre,
            "apellido": estudiante.apellido,
            "cedula": estudiante.cedula,
            "telefono": estudiante.telefono_movil,
            "correo": estudiante.correo_electronico,
            "direccion": estudiante.direccion,
            "edad": estudiante.edad,
            "nivel_educativo": estudiante.nivel_educativo,
            "sexo": estudiante.sexo or "",
            "nacionalidad": estudiante.nacionalidad or "",
            "fecha_nacimiento": estudiante.fecha_nacimiento.isoformat() if estudiante.fecha_nacimiento else "",
            "nombre_emergencia": estudiante.nombre_emergencia or "",
            "telefono_emergencia": estudiante.telefono_emergencia or "",
            "activo": estudiante.activo,
        }

    def get(self, request):
        usuario = request.user
        rol = usuario.rol_nombre

        data = {
            "rol": rol,
            "mi_perfil": None,
            "instructor": None,
            "estudiantes": [],
            "instructores": [],
        }

        if rol in ['admin', 'secretaria']:
            instructores = Instructor.objects.all()

            estudiantes = Estudiante.objects.all()

            data["instructores"] = [
                self.serializar_instructor(request, instructor)
                for instructor in instructores
            ]

            data["estudiantes"] = [
                self.serializar_estudiante(estudiante)
                for estudiante in estudiantes
            ]

            return Response(data)

        if rol == 'instructor':
            instructor = usuario.instructor

            if instructor:
                data["mi_perfil"] = self.serializar_instructor(request, instructor)

                estudiantes_ids = Calendario.objects.filter(
                    instructor=instructor
                ).values_list(
                    'matricula__estudiante_id',
                    flat=True
                ).distinct()

                estudiantes = Estudiante.objects.filter(id__in=estudiantes_ids)

                data["estudiantes"] = [
                    self.serializar_estudiante(estudiante)
                    for estudiante in estudiantes
                ]

            return Response(data)

        if rol == 'estudiante':
            estudiante = usuario.estudiante

            if estudiante:
                data["mi_perfil"] = self.serializar_estudiante(estudiante)

                clase = Calendario.objects.filter(
                    matricula__estudiante=estudiante
                ).select_related(
                    'instructor'
                ).first()

                if clase and clase.instructor:
                    data["instructor"] = self.serializar_instructor(
                        request,
                        clase.instructor
                    )

            return Response(data)

        return Response(data)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exportar_reporte_instructores_policial(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Instructores"

    ws.merge_cells("A1:Q1")
    ws["A1"] = "REPORTE DE INSTRUCTORES - TRÁNSITO POLICÍA NACIONAL"
    ws["A1"].font = Font(size=14, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

    encabezados = [
        "No.",
        "Foto",
        "Nombres y Apellidos",
        "Identificación",
        "Nacionalidad",
        "Dirección",
        "Teléfonos",
        "Nivel Escolar",
        "Antecedentes Penales",
        "Centro de Trabajo",
        "Cargo",
        "Categoría Licencia",
        "Curso Aprobado para Instructor",
        "Fecha de Ingreso",
        "Fecha de Salida",
        "Motivo de la Salida",
        "Infracciones / Resoluciones",
    ]

    fila_encabezado = 3

    header_fill = PatternFill("solid", fgColor="4F81BD")
    thin = Side(border_style="thin", color="A6A6A6")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col, titulo in enumerate(encabezados, start=1):
        celda = ws.cell(row=fila_encabezado, column=col)
        celda.value = titulo
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = header_fill
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celda.border = border

    instructores = Instructor.objects.order_by("nombre", "apellido")

    fila = 4

    for index, instructor in enumerate(instructores, start=1):
        ws.row_dimensions[fila].height = 65

        ws.cell(row=fila, column=1, value=index)

        if instructor.foto:
            try:
                ruta_foto = instructor.foto.path

                if os.path.exists(ruta_foto):
                    imagen = ExcelImage(ruta_foto)
                    imagen.width = 55
                    imagen.height = 55
                    ws.add_image(imagen, f"B{fila}")
            except Exception:
                pass

        nombre_completo = f"{instructor.nombre or ''} {instructor.apellido or ''}".strip()

        ws.cell(row=fila, column=3, value=nombre_completo)
        ws.cell(row=fila, column=4, value=instructor.cedula or "")
        ws.cell(row=fila, column=5, value=instructor.nacionalidad or "")
        ws.cell(row=fila, column=6, value=instructor.direccion or "")
        ws.cell(row=fila, column=7, value=instructor.numero_telefono or "")
        ws.cell(row=fila, column=8, value=instructor.nivel_escolar or "")
        ws.cell(row=fila, column=9, value=instructor.antecedentes_penales or "")
        ws.cell(row=fila, column=10, value=instructor.centro_trabajo or "")
        ws.cell(row=fila, column=11, value=instructor.cargo or "")
        ws.cell(
            row=fila,
            column=12,
            value=instructor.categoria_instructor or ""
        )
        ws.cell(row=fila, column=13, value=instructor.curso_aprobado_instructor or "")
        ws.cell(row=fila, column=14, value=instructor.fecha_ingreso.strftime("%d/%m/%Y") if instructor.fecha_ingreso else "")
        ws.cell(row=fila, column=15, value=instructor.fecha_salida.strftime("%d/%m/%Y") if instructor.fecha_salida else "")
        ws.cell(row=fila, column=16, value=instructor.motivo_salida or "")
        ws.cell(row=fila, column=17, value=instructor.infracciones_resoluciones or "")

        for col in range(1, 18):
            celda = ws.cell(row=fila, column=col)
            celda.border = border
            celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        fila += 1

    anchos = {
        "A": 8,
        "B": 14,
        "C": 28,
        "D": 22,
        "E": 18,
        "F": 35,
        "G": 18,
        "H": 20,
        "I": 22,
        "J": 25,
        "K": 18,
        "L": 20,
        "M": 30,
        "N": 18,
        "O": 18,
        "P": 35,
        "Q": 35,
    }

    for columna, ancho in anchos.items():
        ws.column_dimensions[columna].width = ancho

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="reporte_instructores_policial.xlsx"'

    wb.save(response)

    return response
