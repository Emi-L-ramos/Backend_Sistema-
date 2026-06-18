# app_escuela/api/views.py
import math
import logging
import os
import base64
import tempfile

from copy import copy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import models, transaction
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import status, viewsets, serializers
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import (
    WD_TABLE_ALIGNMENT,
    WD_CELL_VERTICAL_ALIGNMENT,
    WD_ROW_HEIGHT_RULE,
)
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

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
    PagoInstructor,
    CargoInstitucional,
    SubtemaPlanEstudio,
    TemaPlanEstudio,
    ProgresoTema,
    ProgresoClaseTema,
    Notificacion,
    HistorialPlanEstudio,
)

from .serializers import (
    RolSerializer,
    UserSerializer,
    CargoInstitucionalSerializer,
    EstudianteSerializer,
    InstructorSerializer,
    CategoriaVehiculoSerializer,
    MatriculaSerializer,
    ReciboSerializer,
    CalendarioSerializer,
    CrearBloqueCitasSerializer,
    CrearCalendarioManualSerializer,
    AsistenciaSerializer,
    NotasSerializer,
    ValorCursoSerializer,
    PreguntaExamenTeoricoSerializer,
    ExamenTeoricoSerializer,
    PreguntaExamenEstudianteSerializer,
    RespuestaEnviarExamenSerializer,
    RespuestaExamenTeoricoSerializer,
    PagoInstructorSerializer,
    PlanEstudioSerializer,
    ProgresoTemaSerializer,
    NotificacionSerializer,
)

logging.getLogger("PIL").setLevel(logging.WARNING)

def obtener_rol(user):
    return str(getattr(user, 'rol_nombre', '') or '').lower()


def es_admin(user):
    rol = obtener_rol(user)
    return (
        rol in ['admin', 'administrador']
        or user.is_staff
        or user.is_superuser
    )

def es_instructor(user):
    return obtener_rol(user) == 'instructor' and getattr(user, 'instructor_id', None)


def es_estudiante(user):
    return obtener_rol(user) == 'estudiante' and getattr(user, 'estudiante_id', None)

def validar_plan_completado_para_examen(matricula):
    tipo = str(getattr(matricula, 'tipo_curso', '') or '').strip().lower()

    progresos = ProgresoTema.objects.filter(matricula=matricula)
    total_temas = progresos.count()

    if total_temas == 0:
        return {
            'completo': False,
            'error': 'El estudiante no tiene temas asignados en su plan de estudio.',
            'progreso': '0/0',
        }

    if tipo in ['intermedio', 'avanzado']:
        progreso = progresos.first()

        clases = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False,
        ).exclude(
            estado='cancelada'
        )

        total_clases = clases.count()

        if total_clases == 0:
            return {
                'completo': False,
                'error': 'El estudiante no tiene clases asignadas.',
                'progreso': '0/0',
            }

        checks_completados = ProgresoClaseTema.objects.filter(
            progreso_tema=progreso,
            calendario__in=clases,
            estudiante_completado=True,
            instructor_completado=True,
            completado=True,
        ).count()

        completo = checks_completados >= total_clases

        return {
            'completo': completo,
            'error': (
                f'No se puede habilitar el examen porque aún no ha completado '
                f'todos los checks diarios. Progreso: {checks_completados}/{total_clases} clases.'
            ),
            'progreso': f'{checks_completados}/{total_clases}',
        }

    completados = progresos.filter(
        estudiante_completado=True,
        instructor_completado=True,
    ).count()

    completo = completados >= total_temas

    return {
        'completo': completo,
        'error': (
            f'No se puede habilitar el examen porque el plan de estudio '
            f'aún no está completo. Progreso: {completados}/{total_temas} temas.'
        ),
        'progreso': f'{completados}/{total_temas}',
    }

def generar_progreso_plan(matricula):
    if not matricula.plan_de_estudio:
        return

    temas = TemaPlanEstudio.objects.filter(
        plan_estudio=matricula.plan_de_estudio,
        activo=True
    ).order_by(
        'orden',
        'id'
    )

    for index, tema in enumerate(temas, start=1):
        ProgresoTema.objects.get_or_create(
            matricula=matricula,
            tema=tema,
            defaults={
                'orden_general': index,
                'desbloqueado': index == 1,
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

def desactivar_usuario(usuario):
    if not usuario:
        return

    usuario.is_active = False
    usuario.save(update_fields=['is_active'])

    Token.objects.filter(user=usuario).delete()


def desactivar_usuarios_estudiante(estudiante):
    usuarios = estudiante.usuarios.all()

    for usuario in usuarios:
        desactivar_usuario(usuario)

    estudiante.activo = False
    estudiante.save(update_fields=['activo'])


def desactivar_usuarios_instructor(instructor):
    usuarios = instructor.usuarios.all()

    for usuario in usuarios:
        desactivar_usuario(usuario)

def obtener_foto_instructor(instructor):
    if not instructor:
        return None

    return getattr(instructor, "foto_base64", None)


def crear_archivo_temporal_desde_base64(foto_base64):
    if not foto_base64:
        return None

    try:
        formato, imgstr = foto_base64.split(";base64,")
        extension = formato.split("/")[-1]

        archivo = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{extension}"
        )

        archivo.write(base64.b64decode(imgstr))
        archivo.close()

        return archivo.name

    except Exception:
        return None
    
def obtener_ruta_foto_instructor_para_excel(instructor):
    if not instructor:
        return None

    return crear_archivo_temporal_desde_base64(
        getattr(instructor, "foto_base64", None)
    )

class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer
    permission_classes = [IsAuthenticated]
    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)



class CategoriaVehiculoViewSet(viewsets.ModelViewSet):
    queryset = CategoriaVehiculo.objects.all()
    serializer_class = CategoriaVehiculoSerializer
    permission_classes = [IsAuthenticated]
    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)


class EstudianteViewSet(viewsets.ModelViewSet):
    queryset = Estudiante.objects.all()
    serializer_class = EstudianteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Estudiante.objects.all().order_by('-id')
        buscar = self.request.query_params.get('buscar')

        if es_admin(user):
            pass

        elif es_instructor(user):
            estudiantes_ids = Calendario.objects.filter(
                instructor_id=user.instructor_id,
                es_examen=False
            ).exclude(
                estado='cancelada'
            ).values_list(
                'matricula__estudiante_id',
                flat=True
            ).distinct()

            queryset = queryset.filter(id__in=estudiantes_ids)

        elif es_estudiante(user):
            queryset = queryset.filter(id=user.estudiante_id)

        else:
            return Estudiante.objects.none()

        if buscar:
            queryset = queryset.filter(
                Q(nombre__icontains=buscar) |
                Q(apellido__icontains=buscar) |
                Q(cedula__icontains=buscar)
            )

        return queryset
    
    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        total = Estudiante.objects.count()
        activos = Estudiante.objects.filter(activo=True).count()
        inactivos = Estudiante.objects.filter(activo=False).count()

        return Response({
            'total': total,
            'activos': activos,
            'inactivos': inactivos,
        })

class PlanEstudioViewSet(viewsets.ModelViewSet):

    serializer_class = PlanEstudioSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)

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

    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)

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
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Instructor.objects.all().order_by('-id')
        activo = self.request.query_params.get('activo')

        if activo == 'true':
            queryset = queryset.filter(activo=True)

        if activo == 'false':
            queryset = queryset.filter(activo=False)

        return queryset

    @action(detail=True, methods=['post'], url_path='despedir')
    def despedir(self, request, pk=None):
        instructor = self.get_object()

        fecha_salida = request.data.get('fecha_salida') or timezone.now().date()
        motivo_salida = request.data.get('motivo_salida') or 'Instructor desactivado por administración.'

        instructor.fecha_salida = fecha_salida
        instructor.motivo_salida = motivo_salida
        instructor.activo = False
        instructor.save(update_fields=['fecha_salida', 'motivo_salida', 'activo'])

        desactivar_usuarios_instructor(instructor)

        return Response({
            'message': 'Instructor desactivado correctamente. Su usuario ya no puede acceder.',
            'instructor': self.get_serializer(instructor).data
        })


class MatriculaViewSet(viewsets.ModelViewSet):
    queryset = Matricula.objects.select_related('estudiante').all()
    serializer_class = MatriculaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = Matricula.objects.select_related(
            'estudiante'
        ).all().order_by('-id')

        if es_admin(user):
            pass

        elif es_instructor(user):
            matriculas_ids = Calendario.objects.filter(
                instructor_id=user.instructor_id,
                es_examen=False
            ).exclude(
                estado='cancelada'
            ).values_list(
                'matricula_id',
                flat=True
            ).distinct()

            queryset = queryset.filter(id__in=matriculas_ids)

        elif es_estudiante(user):
            queryset = queryset.filter(estudiante_id=user.estudiante_id)

        else:
            return Matricula.objects.none()

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
    
    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede crear matrículas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)


    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede editar matrículas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede editar matrículas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede eliminar matrículas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)
    


    @action(detail=False, methods=['get'], url_path='buscar-estudiante')
    def buscar_estudiante(self, request):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para buscar estudiantes.'},
                status=status.HTTP_403_FORBIDDEN
            )
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
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = Recibo.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'valor_curso',
        ).all().order_by('-id')

        if es_admin(user):
            return queryset

        if es_estudiante(user):
            return queryset.filter(
                matricula__estudiante_id=user.estudiante_id
            )

        return Recibo.objects.none()

    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede registrar recibos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede editar recibos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede editar recibos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede eliminar recibos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)
    

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user

        queryset = Usuario.objects.select_related(
            'rol',
            'estudiante',
            'instructor',
        ).all().order_by('id')

        if es_admin(user):
            return queryset

        return queryset.filter(id=user.id)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede crear usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede editar usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede editar usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede eliminar usuarios.'},
                status=status.HTTP_403_FORBIDDEN
            )

        usuario = self.get_object()
        instructor = getattr(usuario, 'instructor', None)

        self.perform_destroy(usuario)

        if instructor:
            instructor.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='crear-estudiante')
    def crear_usuario_estudiante(self, request):
        matricula_id = request.data.get('matricula_id')
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede crear usuarios de estudiantes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
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

        if matricula.estudiante.usuarios.filter(
            rol__nombre__iexact='estudiante'
        ).exists():
            return Response(
                {'error': 'Este estudiante ya tiene usuario.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        data['matricula_id'] = matricula.id
        data.setdefault('first_name', matricula.estudiante.nombre)
        data.setdefault('last_name', matricula.estudiante.apellido)
        data.setdefault('email', matricula.estudiante.correo_electronico)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

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

    def perform_update(self, serializer):
        instancia_anterior = self.get_object()
        calendario = serializer.save()

        if (
            calendario.es_examen
            and calendario.estado == 'completada'
            and instancia_anterior.estado != 'completada'
        ):
            matricula = calendario.matricula
            estudiante = matricula.estudiante

            matricula.estado = 'finalizado'
            matricula.save(update_fields=['estado'])

            desactivar_usuarios_estudiante(estudiante)

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
    
    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede crear citas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)


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
    
 ## En la copia no me sale esta funcion
    
    @action(detail=True, methods=['post'], url_path='completar-examen')
    def completar_examen(self, request, pk=None):
        calendario = self.get_object()

        if not calendario.es_examen:
            return Response(
                {'error': 'Esta cita no corresponde a un examen policial.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if calendario.estado == 'completada':
            return Response(
                {'error': 'Este examen ya fue marcado como completado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            calendario.estado = 'completada'
            calendario.save(update_fields=['estado'])

            matricula = calendario.matricula
            estudiante = matricula.estudiante

            matricula.estado = 'finalizado'
            matricula.save(update_fields=['estado'])

            desactivar_usuarios_estudiante(estudiante)

        return Response({
            'message': 'Examen policial completado. El estudiante fue desactivado correctamente.',
            'calendario': CalendarioSerializer(calendario).data,
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

        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede crear bloques de citas.'},
                status=status.HTTP_403_FORBIDDEN
            )


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
                estado__in=['pendiente']
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

            progresos = list(
                ProgresoTema.objects.filter(
                    matricula=matricula
                ).select_related(
                    'tema',
                    'tema__plan_estudio'
                ).order_by(
                    'orden_general',
                    'id'
                )
            )

        pendientes = [
            progreso for progreso in progresos
            if not progreso.completado
        ]

        for progreso in pendientes:
            progreso.desbloqueado = False
            progreso.save(update_fields=['desbloqueado'])

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
    
    @action(detail=False, methods=['post'], url_path='crear-manual')
    def crear_calendario_manual(self, request):
        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede crear calendario manual.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CrearCalendarioManualSerializer(data=request.data)
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

        fechas = sorted(data['fechas'])

        for fecha_clase in fechas:
            choque = Calendario.objects.filter(
                instructor=instructor,
                fecha=fecha_clase,
                hora_inicio__lt=hora_fin,
                hora_fin__gt=hora_inicio,
            ).exclude(
                estado='cancelada'
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

            progresos = list(
                ProgresoTema.objects.filter(
                    matricula=matricula
                ).select_related(
                    'tema',
                    'tema__plan_estudio'
                ).order_by(
                    'orden_general',
                    'id'
                )
            )

        pendientes = [
            progreso for progreso in progresos
            if not progreso.completado
        ]

        for progreso in pendientes:
            progreso.desbloqueado = False
            progreso.save(update_fields=['desbloqueado'])

        return Response(
            {
                'message': f'Calendario manual de {len(creadas)} clases creado correctamente.',
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

        if not es_admin(request.user):
            return Response(
                {'error': 'Solo el administrador puede modificar el calendario.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not instructor_id:
            return super().partial_update(request, *args, **kwargs)

        if aplicar_a == 'pendientes':
            clases = Calendario.objects.filter(
                matricula=instance.matricula,
                estado='pendiente',
                fecha__gte=instance.fecha,
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

        cantidad_examenes = Calendario.objects.filter(
            matricula=matricula,
            es_examen=True,
        ).count()

        if cantidad_examenes:
            return Response(
                {
                    'error': 'Este estudiante ya tiene el máximo de 3 exámenes policiales asignados.'
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
    'As_estudiante',
    'As_calendario',
    'As_calendario__matricula',
    'As_calendario__matricula__estudiante',
    'As_calendario__instructor',
    ).all()
    serializer_class = AsistenciaSerializer
    permission_classes = [IsAuthenticated]


    def list(self, request, *args, **kwargs):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''
        hoy = timezone.localdate()

        fecha_param = request.query_params.get('fecha')
        fecha_inicio_param = request.query_params.get('fecha_inicio')
        fecha_fin_param = request.query_params.get('fecha_fin')

        if fecha_param:
            fecha_inicio_param = fecha_param
            fecha_fin_param = fecha_param

        if not fecha_inicio_param:
            fecha_inicio_param = hoy.isoformat()

        if not fecha_fin_param:
            fecha_fin_param = fecha_inicio_param

        try:
            fecha_inicio = datetime.strptime(
                fecha_inicio_param,
                '%Y-%m-%d'
            ).date()

            fecha_fin = datetime.strptime(
                fecha_fin_param,
                '%Y-%m-%d'
            ).date()

        except ValueError:
            return Response(
                {
                    'error': 'Las fechas deben tener el formato YYYY-MM-DD.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if fecha_fin < fecha_inicio:
            return Response(
                {
                    'error': 'La fecha final no puede ser menor que la fecha inicial.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        clases_base = Calendario.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'instructor'
        ).filter(
            es_examen=False,
            matricula__estado='matriculado'
        ).order_by(
            'matricula_id',
            'numero_clase',
            'fecha',
            'hora_inicio'
        )

        if rol == 'instructor':
            if not user.instructor_id:
                return Response([])

            clases_base = clases_base.filter(
                instructor_id=user.instructor_id
            )

        elif rol == 'estudiante':
            if not user.estudiante_id:
                return Response([])

            clases_base = clases_base.filter(
                matricula__estudiante_id=user.estudiante_id
            )
        
        elif rol not in ['admin', 'administrador'] and not user.is_staff and not user.is_superuser:
            return Response([])
        
        matriculas_en_rango = clases_base.filter(
            fecha__gte=fecha_inicio,
            fecha__lte=fecha_fin
        ).values_list(
            'matricula_id',
            flat=True
        ).distinct()

        clases = clases_base.filter(
            matricula_id__in=matriculas_en_rango
        ).order_by(
            'matricula_id',
            'numero_clase',
            'fecha',
            'hora_inicio'
        )


        asistencias = Asistencia.objects.select_related(
            'As_estudiante',
            'As_calendario'
        ).filter(
            As_calendario__in=clases
        )

        asistencias_por_clase = {
            asistencia.As_calendario_id: asistencia
            for asistencia in asistencias
        }

        resultado = {}

        for clase in clases:
            estudiante = clase.matricula.estudiante
            matricula_id = clase.matricula_id

            if matricula_id not in resultado:
                instructor = clase.instructor

                instructor_nombre = "No asignado"

                if instructor:
                    instructor_nombre = (
                        f"{instructor.nombre or ''} {instructor.apellido or ''}"
                    ).strip()

                    if not instructor_nombre:
                        usuario = instructor.usuarios.first()
                        if usuario:
                            instructor_nombre = (
                                f"{usuario.first_name or ''} {usuario.last_name or ''}"
                            ).strip() or usuario.username

                    if not instructor_nombre:
                        instructor_nombre = f"Instructor {instructor.id}"

                resultado[matricula_id] = {
                    'matricula_id': matricula_id,
                    'nombre': f'{estudiante.nombre} {estudiante.apellido}',
                    'cedula': estudiante.cedula,
                    'tipo_curso': clase.matricula.tipo_curso,
                    'instructor_id': instructor.id if instructor else None,
                    'instructor_nombre': instructor_nombre,
                    'conductor': instructor_nombre,
                    'asistencias': {},
                    'porcentaje': 0,
                }

            asistencia = asistencias_por_clase.get(clase.id)

            if asistencia:
                estado = asistencia.estado
                asistencia_id = asistencia.id
                justificado_por_admin = asistencia.justificado_por_admin
            else:
                estado = 'pendiente'
                asistencia_id = None
                justificado_por_admin = False
            
            en_rango = fecha_inicio <= clase.fecha <= fecha_fin
            es_hoy = clase.fecha == hoy
            es_pasado = clase.fecha < hoy
            es_futuro = clase.fecha > hoy

            es_admin_asistencia = (
                rol in ['admin', 'administrador']
                or user.is_staff
                or user.is_superuser
            )

            puede_marcar = (
                es_hoy
                and en_rango
                and asistencia is None
                and clase.estado in ['pendiente', 'reprogramada']
                and (
                    es_admin_asistencia
                    or (
                        rol == 'instructor'
                        and clase.instructor_id == getattr(user, 'instructor_id', None)
                    )
                )
            )
              

            resultado[matricula_id]['asistencias'][str(clase.numero_clase)] = {
                'id': clase.id,
                'asistencia_id': asistencia_id,
                'fecha': clase.fecha,
                'hora_inicio': clase.hora_inicio,
                'hora_fin': clase.hora_fin,
                'numero_clase': clase.numero_clase,
                'estado': estado,
                'justificado_por_admin': justificado_por_admin,
                'instructor_id': clase.instructor.id if clase.instructor else None,
                'instructor_nombre': instructor_nombre,

                #'observacion': observacion,
                'km_inicial': asistencia.km_inicial if asistencia else None,
                'km_final': asistencia.km_final if asistencia else None,
                'km_recorridos': asistencia.km_recorridos if asistencia else 0,

                'en_rango': en_rango,
                'es_hoy': es_hoy,
                'es_pasado': es_pasado,
                'es_futuro': es_futuro,
                'puede_marcar': puede_marcar,
                'bloqueado': not puede_marcar,

            }


        for item in resultado.values():
            asistencias_estudiante = item['asistencias'].values()

            total_clases_validas = 0
            total_asistidas = 0

            for asistencia in asistencias_estudiante:
                estado = asistencia.get('estado')

                if estado == 'justificado':
                    continue

                total_clases_validas += 1

                if estado == 'asistio':
                    total_asistidas += 1

            item['porcentaje'] = (
                round((total_asistidas / total_clases_validas) * 100)
                if total_clases_validas > 0
                else 0
            )

        return Response(list(resultado.values()))
    
    @action(detail=False, methods=['post'], url_path='marcar')
    def marcar(self, request):
        clase_id = request.data.get('clase_id')
        estado = request.data.get('estado')
        observacion = request.data.get('observacion', '')
        km_inicial = request.data.get('km_inicial')
        km_final = request.data.get('km_final')

        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        es_admin_asistencia = (
            rol in ['admin', 'administrador']
            or user.is_staff
            or user.is_superuser
        )

        es_usuario_instructor = rol == 'instructor'

        if not es_admin_asistencia and not es_usuario_instructor:
            return Response(
                {'error': 'Solo el instructor o el administrador pueden marcar asistencia.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if estado not in ['asistio', 'falto']:
            return Response(
                {'error': 'Solo se puede marcar asistió o faltó.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            clase = Calendario.objects.select_related(
                'matricula',
                'matricula__estudiante',
                'instructor'
            ).get(id=clase_id)
        except Calendario.DoesNotExist:
            return Response(
                {'error': 'Clase no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if es_usuario_instructor and not es_admin_asistencia:
            instructor_usuario = getattr(user, 'instructor', None)

            if not instructor_usuario:
                return Response(
                    {'error': 'El usuario actual no tiene instructor asignado.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if clase.instructor_id != instructor_usuario.id:
                return Response(
                    {'error': 'No puedes marcar asistencia de una clase que no te pertenece.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if estado == 'asistio':
            if km_inicial in [None, '']:
                    return Response(
                    {'error': 'Debe ingresar el km inicial.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                km_inicial = Decimal(str(km_inicial))
            except Exception:
                return Response(
                    {'error': 'El km inicial debe ser numérico.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            km_final = None

            if not observacion and es_admin_asistencia:
                observacion = 'Asistencia registrada por administrador.'
        else:
            km_inicial = None
            km_final = None

        hoy = timezone.localdate()

        if clase.fecha != hoy:
            return Response(
                {'error': 'Solo se puede marcar asistencia el día exacto de la clase.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if clase.estado not in ['pendiente', 'reprogramada']:
            return Response(
                {'error': 'Esta clase ya no está disponible para marcar asistencia.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asistencia, created = Asistencia.objects.update_or_create(
            As_calendario=clase,
            defaults={
                'As_estudiante': clase.matricula.estudiante,
                'estado': estado,
                'observacion': observacion,
                'justificado_por_admin': False,
                'km_inicial': km_inicial,
                'km_final': km_final,
            }
        )

        if estado == 'asistio':
            clase.estado = 'completada'
        else:
            clase.estado = 'inasistencia'

        clase.save(update_fields=['estado'])

        serializer = self.get_serializer(asistencia)

        return Response({
            'success': True,
            'message': 'Asistencia registrada correctamente.',
            'data': serializer.data
        })
    
    @action(detail=False, methods=['post'], url_path='finalizar-km')
    def finalizar_km(self, request):
        asistencia_id = request.data.get('asistencia_id')
        km_final = request.data.get('km_final')

        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        es_admin_asistencia = (
            rol in ['admin', 'administrador']
            or user.is_staff
            or user.is_superuser
        )

        es_usuario_instructor = rol == 'instructor'

        if not es_admin_asistencia and not es_usuario_instructor:
            return Response(
                {'error': 'Solo el instructor o el administrador pueden finalizar kilometraje.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not asistencia_id:
            return Response(
                {'error': 'Debe enviar la asistencia.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            asistencia = Asistencia.objects.select_related(
                'As_calendario',
                'As_calendario__instructor'
            ).get(id=asistencia_id)
        except Asistencia.DoesNotExist:
            return Response(
                {'error': 'Asistencia no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if es_usuario_instructor and not es_admin_asistencia:
            instructor_usuario = getattr(user, 'instructor', None)

            if not instructor_usuario:
                return Response(
                    {'error': 'El usuario actual no tiene instructor asignado.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if asistencia.As_calendario.instructor_id != instructor_usuario.id:
                return Response(
                    {'error': 'No puedes finalizar kilometraje de una clase que no te pertenece.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if asistencia.estado != 'asistio':
            return Response(
                {'error': 'Solo clases asistidas pueden finalizar kilometraje.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if km_final in [None, '']:
            return Response(
                {'error': 'Debe ingresar el km final.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            km_final = Decimal(str(km_final))
        except Exception:
            return Response(
                {'error': 'El km final debe ser numérico.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if asistencia.km_inicial is None:
            return Response(
                {'error': 'La asistencia no tiene km inicial.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if km_final < asistencia.km_inicial:
            return Response(
                {'error': 'El km final no puede ser menor al inicial.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asistencia.km_final = km_final
        asistencia.save(update_fields=['km_final'])

        serializer = self.get_serializer(asistencia)

        return Response({
            'success': True,
            'message': 'Kilometraje final registrado.',
            'data': serializer.data
        })
    
    @action(detail=False, methods=['post'], url_path='editar-km')
    def editar_km(self, request):
        asistencia_id = request.data.get('asistencia_id')
        km_inicial = request.data.get('km_inicial')
        km_final = request.data.get('km_final')

        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        es_admin_asistencia = (
            rol in ['admin', 'administrador']
            or user.is_staff
            or user.is_superuser
        )

        es_usuario_instructor = rol == 'instructor'

        if not es_admin_asistencia and not es_usuario_instructor:
            return Response(
                {'error': 'Solo el instructor o el administrador pueden editar kilometraje.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not asistencia_id:
            return Response(
                {'error': 'Debe enviar la asistencia.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            asistencia = Asistencia.objects.select_related(
                'As_calendario',
                'As_calendario__instructor'
            ).get(id=asistencia_id)
        except Asistencia.DoesNotExist:
            return Response(
                {'error': 'Asistencia no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if es_usuario_instructor and not es_admin_asistencia:
            instructor_usuario = getattr(user, 'instructor', None)

            if not instructor_usuario:
                return Response(
                    {'error': 'El usuario actual no tiene instructor asignado.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if asistencia.As_calendario.instructor_id != instructor_usuario.id:
                return Response(
                    {'error': 'No puedes editar kilometraje de una clase que no te pertenece.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if asistencia.estado != 'asistio':
            return Response(
                {'error': 'Solo se puede editar kilometraje de clases asistidas.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if km_inicial in [None, '']:
            return Response(
                {'error': 'Debe ingresar el km inicial.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            km_inicial = Decimal(str(km_inicial))
        except Exception:
            return Response(
                {'error': 'El km inicial debe ser numérico.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if km_final in [None, '']:
            km_final = None
        else:
            try:
                km_final = Decimal(str(km_final))
            except Exception:
                return Response(
                    {'error': 'El km final debe ser numérico.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if km_final < km_inicial:
                return Response(
                    {'error': 'El km final no puede ser menor al inicial.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        asistencia.km_inicial = km_inicial
        asistencia.km_final = km_final
        asistencia.save(update_fields=['km_inicial', 'km_final'])

        serializer = self.get_serializer(asistencia)

        return Response({
            'success': True,
            'message': 'Kilometraje editado correctamente.',
            'data': serializer.data
        })
        
    @action(detail=True, methods=['post'], url_path='justificar')
    def justificar(self, request, pk=None):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        if rol not in ['admin', 'administrador'] and not user.is_staff and not user.is_superuser:
            return Response(
                {'error': 'Solo el administrador puede justificar una inasistencia.'},
                status=status.HTTP_403_FORBIDDEN
            )

        asistencia = self.get_object()

        if asistencia.estado != 'falto':
            return Response(
                {'error': 'Solo se pueden justificar clases marcadas como faltó.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        observacion = request.data.get('observacion', '')

        with transaction.atomic():
            asistencia.estado = 'justificado'
            asistencia.justificado_por_admin = True

            asistencia.save(update_fields=['estado', 'justificado_por_admin'])

            clase_faltada = asistencia.As_calendario

            clase_faltada.estado = 'reprogramada'
            clase_faltada.save(update_fields=['estado'])

            nueva_clase = self.reprogramar_clases_por_justificacion(clase_faltada)

        serializer = self.get_serializer(asistencia)

        return Response({
            'success': True,
            'message': 'Inasistencia justificada. Se agregó un día adicional para recuperar la clase perdida.',
            'data': serializer.data,
            'nueva_clase_id': nueva_clase.id if nueva_clase else None,
        })
        

    def reprogramar_clases_por_justificacion(self, clase_faltada):
        matricula = clase_faltada.matricula
        es_extraordinario = str(matricula.modalidad).lower() == 'extraordinario'

        def siguiente_fecha_valida(fecha_base):
            nueva_fecha = fecha_base + timedelta(days=1)

            while True:
                es_fin_semana = nueva_fecha.weekday() >= 5

                if es_extraordinario and es_fin_semana:
                    return nueva_fecha

                if not es_extraordinario and not es_fin_semana:
                    return nueva_fecha

                nueva_fecha += timedelta(days=1)

        ultima_clase = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False
        ).order_by(
            '-numero_clase'
        ).first()

        ultimo_numero = ultima_clase.numero_clase if ultima_clase else 0

        ultima_fecha = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False
        ).order_by(
            '-fecha',
            '-hora_inicio'
        ).first()

        fecha_base = ultima_fecha.fecha if ultima_fecha else clase_faltada.fecha
        fecha_recuperacion = siguiente_fecha_valida(fecha_base)

        while Calendario.objects.filter(
            instructor=clase_faltada.instructor,
            fecha=fecha_recuperacion,
            hora_inicio__lt=clase_faltada.hora_fin,
            hora_fin__gt=clase_faltada.hora_inicio,
            estado__in=['pendiente', 'reprogramada', 'inasistencia']
        ).exists():
            fecha_recuperacion = siguiente_fecha_valida(fecha_recuperacion)

        nueva_clase = Calendario.objects.create(
            matricula=matricula,
            instructor=clase_faltada.instructor,
            fecha=fecha_recuperacion,
            hora_inicio=clase_faltada.hora_inicio,
            hora_fin=clase_faltada.hora_fin,
            numero_clase=ultimo_numero + 1,
            estado='pendiente',
            es_examen=False,
        )

        return nueva_clase


    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        matriculas = Matricula.objects.select_related(
            'estudiante',
            'plan_de_estudio'
        ).all()

        resultado = []

        for matricula in matriculas:
            clases = Calendario.objects.filter(
                matricula=matricula,
                es_examen=False
            ).order_by('numero_clase')

            asistencias = Asistencia.objects.filter(
                As_calendario__matricula=matricula
            )

            total_marcadas = asistencias.exclude(
                estado='justificado'
            ).count()

            presentes = asistencias.filter(
                estado='asistio'
            ).count()

            porcentaje = (
                round((presentes / total_marcadas) * 100)
                if total_marcadas > 0
                else 0
            )

            resultado.append({
                'matricula_id': matricula.id,
                'nombre': matricula.estudiante.nombre,
                'apellido': matricula.estudiante.apellido,
                'cedula': matricula.estudiante.cedula,
                'plan_estudio': matricula.plan_de_estudio.nombre if matricula.plan_de_estudio else '',
                'tipo_curso': matricula.tipo_curso,
                'total_clases': clases.count(),
                'porcentaje': porcentaje,
            })

        return Response(resultado)
    

    @action(detail=False, methods=['get'], url_path='resumen-km')
    def resumen_km(self, request):
        user = request.user

        asistencias = Asistencia.objects.select_related(
            'As_estudiante',
            'As_calendario',
            'As_calendario__instructor'
        ).filter(
            estado='asistio'
        )

        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin = request.query_params.get('fecha_fin')

        if fecha_inicio and fecha_fin:
            asistencias = asistencias.filter(
                As_calendario__fecha__range=[fecha_inicio, fecha_fin]
            )
        elif fecha_inicio:
            asistencias = asistencias.filter(
                As_calendario__fecha=fecha_inicio
            )

        if es_admin(user):
            pass

        elif es_instructor(user):
            asistencias = asistencias.filter(
                As_calendario__instructor_id=user.instructor_id
            )

        elif es_estudiante(user):
            asistencias = asistencias.filter(
                As_estudiante_id=user.estudiante_id
            )

        else:
            return Response([])

        resultado = {}

        for asistencia in asistencias:
            estudiante = asistencia.As_estudiante
            calendario = asistencia.As_calendario

            if not estudiante or not calendario or not calendario.instructor:
                continue

            instructor = calendario.instructor

            key = f"{estudiante.id}_{instructor.id}"

            if key not in resultado:
                resultado[key] = {
                    'estudiante_id': estudiante.id,
                    'estudiante_nombre': f"{estudiante.nombre} {estudiante.apellido}",
                    'cedula': estudiante.cedula,

                    'instructor_id': instructor.id,
                    'instructor_nombre': f"{instructor.nombre} {instructor.apellido}",

                    'total_clases': 0,
                    'total_km': 0,
                    'detalles': []
                }

            km = float(asistencia.km_recorridos or 0)

            resultado[key]['total_clases'] += 1
            resultado[key]['total_km'] += km

            resultado[key]['detalles'].append({
                'fecha': calendario.fecha,
                'numero_clase': calendario.numero_clase,
                'km_inicial': asistencia.km_inicial,
                'km_final': asistencia.km_final,
                'km_recorridos': asistencia.km_recorridos,
            })

        return Response(list(resultado.values()))
    
    @action(detail=False, methods=['get'], url_path='resumen-estudiante')
    def resumen_estudiante(self, request):
        user = request.user

        if not hasattr(user, 'estudiante') or not user.estudiante:
            return Response({
                'porcentaje': 0,
                'asistidas': 0,
                'total': 0,
            })

        matricula = Matricula.objects.filter(
            estudiante=user.estudiante,
            estado='matriculado'
        ).order_by('-id').first()

        if not matricula:
            return Response({
                'porcentaje': 0,
                'asistidas': 0,
                'total': 0,
            })

        clases_todas = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False
        ).order_by(
            'numero_clase',
            'fecha',
            'hora_inicio'
        )

        primera_clase = clases_todas.first()

        if not primera_clase:
            return Response({
                'porcentaje': 0,
                'asistidas': 0,
                'total': 0,
            })

        inicio = datetime.combine(date.today(), primera_clase.hora_inicio)
        fin = datetime.combine(date.today(), primera_clase.hora_fin)

        horas_por_dia = int((fin - inicio).total_seconds() // 3600)

        if horas_por_dia <= 0:
            horas_por_dia = 1

        if matricula.tipo_curso == 'Principiante':
            horas_totales = 15
        else:
            horas_totales = matricula.horas_reforzamiento or 0

        total_encuentros_oficiales = math.ceil(
            float(horas_totales) / horas_por_dia
        ) if horas_totales else 0

        clases_oficiales = clases_todas.filter(
            numero_clase__lte=total_encuentros_oficiales
        )

        total = clases_oficiales.count()

        asistidas = Asistencia.objects.filter(
            As_calendario__in=clases_oficiales,
            estado='asistio'
        ).count()

        porcentaje = (
            round((asistidas / total) * 100)
            if total > 0
            else 0
        )

        return Response({
            'porcentaje': porcentaje,
            'asistidas': asistidas,
            'total': total,
        })
    
    @action(detail=False, methods=['get'], url_path='fechas-disponibles')
    def fechas_disponibles(self, request):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        clases = Calendario.objects.filter(
            es_examen=False,
            matricula__estado='matriculado'
        ).exclude(
            estado='cancelada'
        )

        if rol == 'instructor':
            if not user.instructor_id:
                return Response([])

            clases = clases.filter(
                instructor_id=user.instructor_id
            )

        elif rol == 'estudiante':
            if not user.estudiante_id:
                return Response([])

            clases = clases.filter(
                matricula__estudiante_id=user.estudiante_id
            )

        elif rol not in ['admin', 'administrador'] and not user.is_staff and not user.is_superuser:
            return Response([])

        fechas = clases.order_by('fecha').values_list(
            'fecha',
            flat=True
        ).distinct()

        return Response([
            fecha.isoformat()
            for fecha in fechas
        ])
    
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
        
        if not Calendario.objects.filter(
            matricula=matricula,
            instructor=request.user.instructor,
            es_examen=False
        ).exists():
            return Response({
                'error': 'No puedes registrar nota de un estudiante que no tienes asignado.'
            }, status=status.HTTP_403_FORBIDDEN)

        if Notas.objects.filter(
            matricula=matricula,
            tipo_nota='practico'
        ).exists():
            return Response({
                'error': 'Ya existe una nota práctica registrada para este estudiante.'
            }, status=status.HTTP_400_BAD_REQUEST)

        validacion_plan = validar_plan_completado_para_examen(matricula)

        if not validacion_plan['completo']:
            return Response({
                'error': (
                    'No se puede registrar la nota porque el estudiante no ha completado '
                    f'el plan de estudio. {validacion_plan["error"]}'
                )
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

    usuario_existente = Usuario.objects.filter(username=username).first()

    if usuario_existente and not usuario_existente.is_active:
        return Response({
            'error': 'Este usuario está desactivado. Contacte al administrador.'
        }, status=403)

    user = authenticate(username=username, password=password)

    if not user:
        return Response({
            'error': 'Credenciales inválidas'
        }, status=401)

    if not user.is_active:
        return Response({
            'error': 'Este usuario está desactivado. Contacte al administrador.'
        }, status=403)

    token, created = Token.objects.get_or_create(user=user)

    return Response({
        'token': token.key,
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'rol': user.rol.nombre if user.rol else 'sin rol',
    })

class DashboardGananciasView(APIView):
    """Endpoint para obtener ganancias mensuales y matriculados"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para ver información del dashboard.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            hoy = datetime.now().date()

            anio_param = request.query_params.get('anio')

            try:
                anio = int(anio_param) if anio_param else hoy.year
            except ValueError:
                anio = hoy.year

            meses_resultado = []

            for mes in range(1, 13):
                total_ganancias = Recibo.objects.filter(
                    fecha_pago__year=anio,
                    fecha_pago__month=mes,
                    tipo_pago__in=['completo', 'anticipo']
                ).aggregate(
                    total=Sum('monto_pagado')
                )['total'] or Decimal('0')

                total_matriculados = Recibo.objects.filter(
                    fecha_pago__year=anio,
                    fecha_pago__month=mes,
                    tipo_pago__in=['completo', 'beneficio']
                ).values(
                    'matricula'
                ).distinct().count()

                meses_resultado.append({
                    'mes': f'{anio}-{mes:02d}',
                    'total': float(total_ganancias),
                    'matriculados': total_matriculados,
                })

            return Response(meses_resultado)

        except Exception as e:
            print(f"Error en DashboardGananciasView: {str(e)}")
            import traceback
            traceback.print_exc()

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


        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para ver información del dashboard.'},
                status=status.HTTP_403_FORBIDDEN
            )
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
            matriculas_con_teorico = set(
                Notas.objects.filter(
                    tipo_nota='teorico'
                ).values_list(
                    'matricula_id',
                    flat=True
                )
            )

            matriculas_con_practico = set(
                Notas.objects.filter(
                    tipo_nota='practico'
                ).values_list(
                    'matricula_id',
                    flat=True
                )
            )

            matriculas_egresadas = matriculas_con_teorico.intersection(
                matriculas_con_practico
            )

            egresados_mes = len(matriculas_egresadas)
            
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
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para ver información del dashboard.'},
                status=status.HTTP_403_FORBIDDEN
            )
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
            ])
    
    def _get_nombre_mes(self, mes_numero):
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        return meses.get(mes_numero, "")

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

        queryset = ProgresoTema.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'tema',
            'tema__plan_estudio'
        ).prefetch_related(
            'tema__subtemas'
        ).order_by(
            'matricula_id',
            'orden_general',
            'id'
        )

        if rol in ['admin', 'administrador'] or user.is_staff or user.is_superuser:
            return queryset

        if rol == 'estudiante' and hasattr(user, 'estudiante') and user.estudiante:
            return queryset.filter(matricula__estudiante=user.estudiante)

        if rol == 'instructor' and hasattr(user, 'instructor') and user.instructor:
            return queryset.filter(
                matricula__clases__instructor=user.instructor
            ).distinct()

        return ProgresoTema.objects.none()
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        progresos = list(queryset)

        matriculas = {
            progreso.matricula_id: progreso.matricula
            for progreso in progresos
        }

        for matricula in matriculas.values():
            self.normalizar_desbloqueo(matricula)

        progresos_preparados = []

        for progreso in progresos:
            progreso.refresh_from_db()
            progresos_preparados.append(
                self.preparar_contexto_diario(progreso)
            )

        serializer = self.get_serializer(
            progresos_preparados,
            many=True
        )

        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        progreso = self.get_object()

        self.normalizar_desbloqueo(progreso.matricula)

        progreso.refresh_from_db()
        progreso = self.preparar_contexto_diario(progreso)

        serializer = self.get_serializer(progreso)

        return Response(serializer.data)

    def es_modo_diario(self, matricula):
        tipo = str(getattr(matricula, 'tipo_curso', '') or '').lower()
        return tipo in ['intermedio', 'avanzado']

    def obtener_clase_habilitada_hoy(self, matricula):
        ahora = timezone.localtime()
        hoy = timezone.localdate()

        clases = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False,
            fecha=hoy
        ).exclude(
            estado='cancelada'
        ).order_by(
            'hora_inicio',
            'id'
        )

        for clase in clases:
            if not clase.hora_inicio:
                continue

            inicio = datetime.combine(clase.fecha, clase.hora_inicio)

            if timezone.is_naive(inicio):
                inicio = timezone.make_aware(
                    inicio,
                    timezone.get_current_timezone()
                )

            momento_habilitado = inicio - timedelta(minutes=10)

            if ahora >= momento_habilitado:
                return clase

        return None

    def obtener_check_diario_actual(self, progreso, crear=False):
        clase = self.obtener_clase_habilitada_hoy(progreso.matricula)

        if not clase:
            return None

        if crear:
            check, _ = ProgresoClaseTema.objects.get_or_create(
                calendario=clase,
                progreso_tema=progreso
            )
            return check

        return ProgresoClaseTema.objects.filter(
            calendario=clase,
            progreso_tema=progreso
        ).first()

    def preparar_contexto_diario(self, progreso):
        if not self.es_modo_diario(progreso.matricula):
            return progreso

        clase = self.obtener_clase_habilitada_hoy(progreso.matricula)
        progreso.calendario_actual = clase
        progreso.habilitado_hoy = bool(clase)

        if clase:
            check, _ = ProgresoClaseTema.objects.get_or_create(
                calendario=clase,
                progreso_tema=progreso
            )
            progreso.check_dia_actual = check
        else:
            progreso.check_dia_actual = None

        return progreso

    def todas_las_clases_diarias_completadas(self, progreso):
        clases = Calendario.objects.filter(
            matricula=progreso.matricula,
            es_examen=False
        ).exclude(
            estado='cancelada'
        )

        total_clases = clases.count()

        if total_clases == 0:
            return False

        total_checks_completados = ProgresoClaseTema.objects.filter(
            progreso_tema=progreso,
            calendario__in=clases,
            estudiante_completado=True,
            instructor_completado=True,
            completado=True
        ).count()

        return total_checks_completados >= total_clases

    def actualizar_estado_global_diario(self, progreso):
        clases = Calendario.objects.filter(
            matricula=progreso.matricula,
            es_examen=False
        ).exclude(
            estado='cancelada'
        )

        total_clases = clases.count()

        if total_clases == 0:
            progreso.estudiante_completado = False
            progreso.instructor_completado = False
            progreso.completado = False
            progreso.save(
                update_fields=[
                    'estudiante_completado',
                    'instructor_completado',
                    'completado',
                ]
            )
            return

        total_checks_completados = ProgresoClaseTema.objects.filter(
            progreso_tema=progreso,
            calendario__in=clases,
            estudiante_completado=True,
            instructor_completado=True,
            completado=True
        ).count()

        plan_diario_completo = total_checks_completados >= total_clases

        progreso.estudiante_completado = plan_diario_completo
        progreso.instructor_completado = plan_diario_completo
        progreso.completado = plan_diario_completo

        if plan_diario_completo:
            progreso.desbloqueado = True

            ahora = timezone.now()

            if not progreso.fecha_estudiante:
                progreso.fecha_estudiante = ahora

            if not progreso.fecha_instructor:
                progreso.fecha_instructor = ahora

            if not progreso.fecha_completado:
                progreso.fecha_completado = ahora
        else:
            progreso.fecha_completado = None

        progreso.save(
            update_fields=[
                'estudiante_completado',
                'instructor_completado',
                'completado',
                'desbloqueado',
                'fecha_estudiante',
                'fecha_instructor',
                'fecha_completado',
            ]
        )

    def normalizar_desbloqueo_diario(self, matricula):
        progresos = list(
            ProgresoTema.objects.filter(
                matricula=matricula
            ).order_by(
                'orden_general',
                'id'
            )
        )

        if not progresos:
            return

        clase = self.obtener_clase_habilitada_hoy(matricula)
        habilitado = bool(clase)

        for index, progreso in enumerate(progresos):
            progreso.desbloqueado = habilitado and index == 0
            progreso.save(update_fields=['desbloqueado'])

            if habilitado and index == 0:
                ProgresoClaseTema.objects.get_or_create(
                    calendario=clase,
                    progreso_tema=progreso
                )

    def normalizar_desbloqueo_principiante(self, matricula):
        hoy = timezone.localdate()

        progresos = list(
            ProgresoTema.objects.filter(
                matricula=matricula
            ).order_by(
                'orden_general',
                'id'
            )
        )

        if not progresos:
            return

        clases = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False
        ).exclude(
            estado='cancelada'
        ).order_by(
            'fecha',
            'hora_inicio'
        )

        primera_clase = clases.first()

        for progreso in progresos:
            progreso.desbloqueado = False
            progreso.save(update_fields=['desbloqueado'])

        if not primera_clase:
            return

        if primera_clase.fecha > hoy:
            return

        clases_hasta_hoy = clases.filter(
            fecha__lte=hoy
        )

        limite_temas = 0

        for clase in clases_hasta_hoy:
            if clase.hora_inicio and clase.hora_fin:
                inicio = datetime.combine(clase.fecha, clase.hora_inicio)
                fin = datetime.combine(clase.fecha, clase.hora_fin)

                horas_por_dia = int((fin - inicio).total_seconds() // 3600)

                if horas_por_dia <= 0:
                    horas_por_dia = 1
            else:
                horas_por_dia = 1

            limite_temas += horas_por_dia

        limite_temas = min(limite_temas, len(progresos))

        completados = [
            progreso for progreso in progresos
            if progreso.completado
            or (
                progreso.estudiante_completado
                and progreso.instructor_completado
            )
        ]

        cantidad_completados = len(completados)

        inicio_bloque = cantidad_completados
        fin_bloque = limite_temas

        for progreso in progresos[inicio_bloque:fin_bloque]:
            if not progreso.completado:
                progreso.desbloqueado = True
                progreso.save(update_fields=['desbloqueado'])

    def normalizar_desbloqueo(self, matricula):
        if self.es_modo_diario(matricula):
            self.normalizar_desbloqueo_diario(matricula)
            return

        self.normalizar_desbloqueo_principiante(matricula)


    def _actualizar_progreso(self, progreso):
        progreso.completado = (
            progreso.estudiante_completado and
            progreso.instructor_completado
        )

        if progreso.completado and not progreso.fecha_completado:
            progreso.fecha_completado = timezone.now()

        progreso.save()

        self._crear_notificacion_pendiente(progreso)
        
    def _obtener_horas_clase_actual(self, progreso):
        clase = Calendario.objects.filter(
            matricula=progreso.matricula,
            es_examen=False
        ).order_by('fecha', 'hora_inicio').first()

        if not clase:
            return 1

        inicio = datetime.combine(clase.fecha, clase.hora_inicio)
        fin = datetime.combine(clase.fecha, clase.hora_fin)

        horas = int((fin - inicio).total_seconds() // 3600)

        return max(horas, 1)

    def _desbloquear_siguiente(self, progreso_actual):
        limite_temas = self._obtener_horas_clase_actual(progreso_actual)

        progresos = list(
            ProgresoTema.objects.filter(
                matricula=progreso_actual.matricula
            ).select_related(
                'tema'
            ).order_by(
                'orden_general',
                'id'
            )
        )

        for progreso in progresos:
            progreso.desbloqueado = False
            progreso.save(update_fields=['desbloqueado'])

        pendientes = [
            progreso for progreso in progresos
            if not progreso.completado
        ]
        bloque_actual = pendientes[:limite_temas]

        bloque_incompleto = any(
            not (
                item.estudiante_completado and
                item.instructor_completado
            )
            for item in bloque_actual
        )

        if bloque_incompleto:
            return

        usuario_estudiante = progreso_actual.matricula.estudiante.usuarios.first()

        for progreso in pendientes[:limite_temas]:
            progreso.desbloqueado = True
            progreso.save(update_fields=['desbloqueado'])


    def _obtener_usuario_estudiante(self, progreso):
        estudiante = progreso.matricula.estudiante

        usuario = estudiante.usuarios.first()

        return usuario


    def _crear_notificacion_pendiente(self, progreso):
        estudiante = progreso.matricula.estudiante
        estudiante_nombre = f"{estudiante.nombre} {estudiante.apellido}".strip()
        usuario_estudiante = self._obtener_usuario_estudiante(progreso)

        if not usuario_estudiante:
            return

        Notificacion.objects.filter(
            estudiante=usuario_estudiante,
            tema=progreso.tema,
            tipo__in=['falta_estudiante', 'falta_instructor'],
            leida=False
        ).update(leida=True)

        if progreso.estudiante_completado and progreso.instructor_completado:
            return

        clase = Calendario.objects.filter(
            matricula=progreso.matricula,
            instructor__isnull=False
        ).select_related('instructor').first()

        instructor_nombre = "Instructor no asignado"

        if clase and clase.instructor:
            instructor_nombre = (
                f"{clase.instructor.nombre or ''} "
                f"{clase.instructor.apellido or ''}"
            ).strip() or "Instructor no asignado"

        if progreso.estudiante_completado and not progreso.instructor_completado:
            Notificacion.objects.update_or_create(
                estudiante=usuario_estudiante,
                tema=progreso.tema,
                tipo='falta_instructor',
                defaults={
                    'mensaje': (
                        f'El instructor "{instructor_nombre}" no ha dado check '
                        f'al tema "{progreso.tema.titulo}" del estudiante '
                        f'"{estudiante_nombre}".'
                    ),
                    'leida': False,
                    'fecha_creacion': timezone.now(),
                }
            )

        elif progreso.instructor_completado and not progreso.estudiante_completado:
            Notificacion.objects.update_or_create(
                estudiante=usuario_estudiante,
                tema=progreso.tema,
                tipo='falta_estudiante',
                defaults={
                    'mensaje': (
                        f'El estudiante "{estudiante_nombre}" no ha dado check '
                        f'al tema "{progreso.tema.titulo}" marcado por el instructor '
                        f'"{instructor_nombre}".'
                    ),
                    'leida': False,
                    'fecha_creacion': timezone.now(),
                }
            )

    def _validar_limite_temas_por_dia(self, progreso):
        ahora = timezone.now()

        inicio_dia = ahora.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        fin_dia = inicio_dia + timedelta(days=1)

        temas_completados_hoy = ProgresoTema.objects.filter(
            matricula=progreso.matricula,
            estudiante_completado=True,
            instructor_completado=True,
            fecha_completado__gte=inicio_dia,
            fecha_completado__lt=fin_dia,
        ).exclude(id=progreso.id).count()

        if temas_completados_hoy >= 2:
            return Response({
                'success': False,
                'error': (
                    'Ya se completaron 2 temas el día de hoy. '
                    'Debe esperar 24 horas para iniciar la siguiente clase.'
                )
            }, status=status.HTTP_400_BAD_REQUEST)

        ultimo_completado = ProgresoTema.objects.filter(
            matricula=progreso.matricula,
            estudiante_completado=True,
            instructor_completado=True,
            fecha_completado__isnull=False,
        ).exclude(id=progreso.id).order_by('-fecha_completado').first()

        if ultimo_completado:
            diferencia = ahora - ultimo_completado.fecha_completado

            # if diferencia < timedelta(hours=24):
            if diferencia < timedelta(minutes=1):
                restante = timedelta(minutes=1) - diferencia
                # restante = timedelta(hours=24) - diferencia
                # horas = int(restante.total_seconds() // 3600)
                # minutos = int((restante.total_seconds() % 3600) // 60)
                horas = int(restante.total_seconds() // 3600)
                minutos = int((restante.total_seconds() % 3600) // 60)

                return Response({
                    'success': False,
                    'error': (
                        f'Debe esperar 24 horas para iniciar la siguiente clase. '
                        f'Faltan aproximadamente {horas} hora(s) y {minutos} minuto(s).'
                    )
                }, status=status.HTTP_400_BAD_REQUEST)

        return None
    
    @action(detail=False, methods=['post'], url_path='actualizar-desbloqueos')
    def actualizar_desbloqueos(self, request):
        matricula_id = request.data.get('matricula_id')

        if not matricula_id:
            return Response({
                'success': False,
                'error': 'Debe enviar la matrícula.'
            }, status=status.HTTP_400_BAD_REQUEST)

        matricula = get_object_or_404(Matricula, id=matricula_id)

        self.normalizar_desbloqueo(matricula)

        return Response({
            'success': True,
            'message': 'Desbloqueos actualizados correctamente.'
        })

    @action(detail=True, methods=['post'], url_path='marcar-estudiante')
    def marcar_estudiante(self, request, pk=None):
        try:
            progreso = self.get_object()

            if self.es_modo_diario(progreso.matricula):
                self.normalizar_desbloqueo(progreso.matricula)
                progreso.refresh_from_db()
                progreso = self.preparar_contexto_diario(progreso)

                if not getattr(progreso, 'habilitado_hoy', False):
                    return Response({
                        'success': False,
                        'error': 'Este tema aún no está disponible para la clase de hoy.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                check_dia = self.obtener_check_diario_actual(
                    progreso,
                    crear=True
                )

                if not check_dia:
                    return Response({
                        'success': False,
                        'error': 'No hay clase habilitada para marcar este tema.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if check_dia.estudiante_completado:
                    return Response({
                        'success': False,
                        'error': 'Ya marcaste este tema como recibido en la clase de hoy.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                with transaction.atomic():
                    check_dia.estudiante_completado = True
                    check_dia.fecha_estudiante = timezone.now()
                    check_dia.save()

                    if check_dia.completado:
                        self.actualizar_estado_global_diario(progreso)
                        mensaje = "Tema completado correctamente para la clase de hoy."
                    else:
                        mensaje = "Tema marcado como recibido para la clase de hoy. Falta confirmación del instructor."

                progreso.refresh_from_db()
                progreso = self.preparar_contexto_diario(progreso)

                serializer = self.get_serializer(progreso)

                return Response({
                    'success': True,
                    'message': mensaje,
                    'data': serializer.data
                })

            if not progreso.desbloqueado:
                return Response({
                    'success': False,
                    'error': 'Este tema aún no está disponible.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if progreso.estudiante_completado:
                return Response({
                    'success': False,
                    'error': 'Ya habías marcado este tema como recibido'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                progreso.estudiante_completado = True
                progreso.fecha_estudiante = timezone.now()

                if progreso.estudiante_completado and progreso.instructor_completado:
                    progreso.completado = True

                    if not progreso.fecha_completado:
                        progreso.fecha_completado = timezone.now()

                progreso.save()

                if progreso.estudiante_completado and progreso.instructor_completado:
                    Notificacion.objects.filter(
                        estudiante=self._obtener_usuario_estudiante(progreso),
                        tema=progreso.tema,
                        tipo__in=['falta_estudiante', 'falta_instructor'],
                        leida=False
                    ).update(leida=True)
                    self.normalizar_desbloqueo(progreso.matricula)
                else:
                    self._crear_notificacion_pendiente(progreso)

                if progreso.instructor_completado:
                    mensaje = "Tema completado correctamente."
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

            if self.es_modo_diario(progreso.matricula):
                self.normalizar_desbloqueo(progreso.matricula)
                progreso.refresh_from_db()
                progreso = self.preparar_contexto_diario(progreso)

                if not getattr(progreso, 'habilitado_hoy', False):
                    return Response({
                        'success': False,
                        'error': 'Este tema aún no está disponible para la clase de hoy.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                check_dia = self.obtener_check_diario_actual(
                    progreso,
                    crear=True
                )

                if not check_dia:
                    return Response({
                        'success': False,
                        'error': 'No hay clase habilitada para marcar este tema.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if check_dia.instructor_completado:
                    return Response({
                        'success': False,
                        'error': 'Ya marcaste este tema como dado en la clase de hoy.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                with transaction.atomic():
                    check_dia.instructor_completado = True
                    check_dia.fecha_instructor = timezone.now()
                    check_dia.save()

                    if check_dia.completado:
                        self.actualizar_estado_global_diario(progreso)
                        mensaje = "Tema completado correctamente para la clase de hoy."
                    else:
                        mensaje = "Tema marcado como dado para la clase de hoy. Falta confirmación del estudiante."

                progreso.refresh_from_db()
                progreso = self.preparar_contexto_diario(progreso)

                serializer = self.get_serializer(progreso)

                return Response({
                    'success': True,
                    'message': mensaje,
                    'data': serializer.data
                })

            if not progreso.desbloqueado:
                return Response({
                    'success': False,
                    'error': 'Este tema aún no está disponible.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if progreso.instructor_completado:
                return Response({
                    'success': False,
                    'error': 'Ya habías marcado este tema como dado'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                progreso.instructor_completado = True
                progreso.fecha_instructor = timezone.now()

                if progreso.estudiante_completado and progreso.instructor_completado:
                    progreso.completado = True

                    if not progreso.fecha_completado:
                        progreso.fecha_completado = timezone.now()

                progreso.save()

                if progreso.estudiante_completado and progreso.instructor_completado:
                    Notificacion.objects.filter(
                        estudiante=self._obtener_usuario_estudiante(progreso),
                        tema=progreso.tema,
                        tipo__in=['falta_estudiante', 'falta_instructor'],
                        leida=False
                    ).update(leida=True)
                    self.normalizar_desbloqueo(progreso.matricula)
                else:
                    self._crear_notificacion_pendiente(progreso)

                if progreso.estudiante_completado:
                    mensaje = "Tema completado correctamente."
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
        rol = str(getattr(request.user, 'rol_nombre', '') or '').lower()

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

        if self.es_modo_diario(progreso.matricula):
            self.normalizar_desbloqueo(progreso.matricula)
            progreso.refresh_from_db()
            progreso = self.preparar_contexto_diario(progreso)

            if not getattr(progreso, 'habilitado_hoy', False):
                return Response({
                    'success': False,
                    'error': 'Este tema aún no está disponible para la clase de hoy.'
                }, status=status.HTTP_400_BAD_REQUEST)

            check_dia = self.obtener_check_diario_actual(
                progreso,
                crear=True
            )

            if not check_dia:
                return Response({
                    'success': False,
                    'error': 'No hay clase habilitada para modificar este tema.'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                old_estudiante = check_dia.estudiante_completado
                old_instructor = check_dia.instructor_completado

                if tipo_check == 'estudiante':
                    check_dia.estudiante_completado = valor
                    check_dia.fecha_estudiante = timezone.now() if valor else None
                else:
                    check_dia.instructor_completado = valor
                    check_dia.fecha_instructor = timezone.now() if valor else None

                if not valor:
                    check_dia.fecha_completado = None

                check_dia.save()

                if check_dia.completado:
                    self.actualizar_estado_global_diario(progreso)

                try:
                    HistorialPlanEstudio.objects.create(
                        progreso_tema=progreso,
                        usuario=request.user,
                        accion='admin_forzar_diario',
                        valor_anterior_estudiante=old_estudiante,
                        valor_anterior_instructor=old_instructor,
                        valor_nuevo_estudiante=check_dia.estudiante_completado,
                        valor_nuevo_instructor=check_dia.instructor_completado
                    )
                except Exception as e:
                    print(f"Error al guardar historial diario: {e}")

            progreso.refresh_from_db()
            progreso = self.preparar_contexto_diario(progreso)

            serializer = self.get_serializer(progreso)

            check_nombre = "estudiante" if tipo_check == 'estudiante' else "instructor"

            return Response({
                'success': True,
                'message': f'Check diario de {check_nombre} actualizado correctamente',
                'data': serializer.data
            })

        with transaction.atomic():
            old_estudiante = progreso.estudiante_completado
            old_instructor = progreso.instructor_completado

            if tipo_check == 'estudiante':
                progreso.estudiante_completado = valor
                progreso.fecha_estudiante = timezone.now() if valor else None
            else:
                progreso.instructor_completado = valor
                progreso.fecha_instructor = timezone.now() if valor else None

            progreso.fecha_admin_edit = timezone.now()

            if not valor:
                progreso.fecha_completado = None

            self._actualizar_progreso(progreso)
            self.normalizar_desbloqueo(progreso.matricula)

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

            usuario_estudiante = progreso.matricula.estudiante.usuarios.first()

            if usuario_estudiante:
                try:
                    Notificacion.objects.update_or_create(
                        estudiante=usuario_estudiante,
                        tema=progreso.tema,
                        tipo='tema_desbloqueado',
                        defaults={
                            'mensaje': (
                                f"Nuevo tema desbloqueado: "
                                f"'{progreso.tema.titulo}'."
                            ),
                            'leida': False
                        }
                    )
                except Exception as e:
                    print(f"Error creando notificación: {e}")

        serializer = self.get_serializer(progreso)

        check_nombre = "estudiante" if tipo_check == 'estudiante' else "instructor"

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

            validacion_plan = validar_plan_completado_para_examen(matricula)

            if not validacion_plan['completo']:
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

            validacion_plan = validar_plan_completado_para_examen(matricula)

            return Response({
                'success': True,
                'matricula_id': matricula.id,
                'plan_completado': validacion_plan['completo'],
                'progreso': validacion_plan['progreso'],
                'mensaje': (
                    'Plan de estudio completado.'
                    if validacion_plan['completo']
                    else validacion_plan['error']
                ),
            })

        except Matricula.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Matrícula no encontrada'
            }, status=status.HTTP_404_NOT_FOUND)
        
    def crear_notificacion_check_pendiente(self, progreso):
        estudiante_usuario = progreso.matricula.estudiante.usuario

        if progreso.estudiante_completado and not progreso.instructor_completado:
            Notificacion.objects.get_or_create(
                estudiante=estudiante_usuario,
                tema=progreso.tema,
                tipo='falta_instructor',
                leida=False,
                defaults={
                    'mensaje': (
                        f'El estudiante marcó como recibido el tema '
                        f'"{progreso.tema.titulo}", pero el instructor aún no lo ha confirmado.'
                    )
                }
            )

        if progreso.instructor_completado and not progreso.estudiante_completado:
            Notificacion.objects.get_or_create(
                estudiante=estudiante_usuario,
                tema=progreso.tema,
                tipo='falta_estudiante',
                leida=False,
                defaults={
                    'mensaje': (
                        f'El instructor marcó como dado el tema '
                        f'"{progreso.tema.titulo}", pero el estudiante aún no lo ha confirmado.'
                    )
                }
            )  

        # def validar_limite_temas_por_dia(self, progreso):
        #     ahora = timezone.now()
        #     inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        #     fin_dia = inicio_dia + timedelta(days=1)

        #     temas_completados_hoy = ProgresoTema.objects.filter(
        #         matricula=progreso.matricula,
        #         estudiante_completado=True,
        #         instructor_completado=True,
        #         fecha_completado__gte=inicio_dia,
        #         fecha_completado__lt=fin_dia,
        #     ).exclude(id=progreso.id).count()

        #     if temas_completados_hoy >= 2:
        #         return Response(
        #             {
        #                 'error': (
        #                     'Ya se completaron 2 temas el día de hoy. '
        #                     'Debe esperar 24 horas para iniciar la siguiente clase.'
        #                 )
        #             },
        #             status=status.HTTP_400_BAD_REQUEST
        #         )

        #     ultimo_completado = ProgresoTema.objects.filter(
        #         matricula=progreso.matricula,
        #         estudiante_completado=True,
        #         instructor_completado=True,
        #         fecha_completado__isnull=False,
        #     ).exclude(id=progreso.id).order_by('-fecha_completado').first()

        #     if ultimo_completado:
        #         diferencia = ahora - ultimo_completado.fecha_completado

        #         if diferencia < timedelta(hours=24):
        #             tiempo_restante = timedelta(hours=24) - diferencia
        #             horas_restantes = int(tiempo_restante.total_seconds() // 3600)

        #             return Response(
        #                 {
        #                     'error': (
        #                         f'Debe esperar 24 horas para iniciar la siguiente clase. '
        #                         f'Faltan aproximadamente {horas_restantes} hora(s).'
        #                     )
        #                 },
        #                 status=status.HTTP_400_BAD_REQUEST
        #             )

        #     return None           


class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para notificaciones del administrador"""

    queryset = Notificacion.objects.all()
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notificacion.objects.all().order_by('-fecha_creacion')

    @action(detail=True, methods=['post'], url_path='marcar-leida')
    def marcar_leida(self, request, pk=None):
        notificacion = self.get_object()
        notificacion.leida = True
        notificacion.save(update_fields=['leida'])

        return Response({
            'success': True,
            'message': 'Notificación marcada como leída'
        })

    @action(detail=False, methods=['get'], url_path='admin-pendientes')
    def admin_pendientes(self, request):
        user = request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ""

        if rol not in ['admin', 'administrador'] and not user.is_staff and not user.is_superuser:
            return Response(
                {'error': 'Solo el administrador puede ver estas notificaciones.'},
                status=status.HTTP_403_FORBIDDEN
            )

        ahora = timezone.now()
        limite_tiempo = ahora - timedelta(hours=23)

        Notificacion.objects.filter(
            leida=False,
            fecha_creacion__lt=limite_tiempo
        ).update(leida=True)

        notificaciones = Notificacion.objects.filter(
            leida=False,
            tipo__in=['falta_estudiante', 'falta_instructor'],
            fecha_creacion__gte=limite_tiempo,
        ).select_related(
            'estudiante',
            'estudiante__estudiante',
            'tema',
        ).order_by('-fecha_creacion')

        resultado = []
        claves_usadas = set()

        for n in notificaciones:
            progreso = ProgresoTema.objects.filter(
                tema=n.tema,
                matricula__estudiante=n.estudiante.estudiante
            ).select_related(
                'matricula',
                'matricula__estudiante',
                'tema'
            ).first()

            if not progreso:
                n.leida = True
                n.save(update_fields=['leida'])
                continue

            if progreso.estudiante_completado and progreso.instructor_completado:
                n.leida = True
                n.save(update_fields=['leida'])
                continue

            if n.tipo == 'falta_estudiante' and progreso.estudiante_completado:
                n.leida = True
                n.save(update_fields=['leida'])
                continue

            if n.tipo == 'falta_instructor' and progreso.instructor_completado:
                n.leida = True
                n.save(update_fields=['leida'])
                continue

            clave = f"{progreso.matricula_id}-{progreso.tema_id}-{n.tipo}"

            if clave in claves_usadas:
                continue

            claves_usadas.add(clave)

            estudiante = progreso.matricula.estudiante
            estudiante_nombre = f"{estudiante.nombre} {estudiante.apellido}".strip()

            quien_falta = "Instructor" if n.tipo == "falta_instructor" else "Estudiante"
            quien_espera = "Estudiante" if n.tipo == "falta_instructor" else "Instructor"

            resultado.append({
                'id': n.id,
                'tipo': n.tipo,
                'tipo_texto': n.get_tipo_display(),
                'estudiante': estudiante_nombre,
                'tema': progreso.tema.titulo if progreso.tema else '',
                'mensaje': n.mensaje,
                'quien_falta': quien_falta,
                'quien_espera': quien_espera,
                'fecha_creacion': n.fecha_creacion,
            })

            if len(resultado) >= 10:
                break

        return Response(resultado)

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

    @action(detail=False, methods=['get'], url_path='mi-progreso')
    def mi_progreso(self, request):
        user = request.user

        estudiante = getattr(user, 'estudiante', None)

        if not estudiante:
            return Response({
                'porcentaje': 0,
                'temas_completados': 0,
                'total_temas': 0,
                'unidad': 'temas',
            })

        matricula = Matricula.objects.select_related(
            'estudiante',
            'plan_de_estudio',
        ).filter(
            estudiante=estudiante,
            estado='matriculado'
        ).order_by('-id').first()

        if not matricula:
            return Response({
                'porcentaje': 0,
                'temas_completados': 0,
                'total_temas': 0,
                'unidad': 'temas',
            })

        tipo = str(matricula.tipo_curso or '').strip().lower()

        progresos = ProgresoTema.objects.filter(
            matricula=matricula
        ).order_by(
            'orden_general',
            'id'
        )

        total_temas = progresos.count()

        if total_temas == 0:
            return Response({
                'porcentaje': 0,
                'temas_completados': 0,
                'total_temas': 0,
                'unidad': 'temas',
            })

        if tipo in ['intermedio', 'avanzado']:
            progreso = progresos.first()

            clases = Calendario.objects.filter(
                matricula=matricula,
                es_examen=False,
            ).exclude(
                estado='cancelada'
            )

            total_clases = clases.count()

            if total_clases == 0:
                return Response({
                    'porcentaje': 0,
                    'temas_completados': 0,
                    'total_temas': 0,
                    'unidad': 'clases',
                })

            checks_completados = ProgresoClaseTema.objects.filter(
                progreso_tema=progreso,
                calendario__in=clases,
                estudiante_completado=True,
                instructor_completado=True,
                completado=True,
            ).count()

            porcentaje = round((checks_completados / total_clases) * 100)

            return Response({
                'porcentaje': porcentaje,
                'temas_completados': checks_completados,
                'total_temas': total_clases,
                'unidad': 'clases',
            })

        temas_completados = progresos.filter(
            estudiante_completado=True,
            instructor_completado=True
        ).count()

        porcentaje = (
            round((temas_completados / total_temas) * 100)
            if total_temas > 0
            else 0
        )

        return Response({
            'porcentaje': porcentaje,
            'temas_completados': temas_completados,
            'total_temas': total_temas,
            'unidad': 'temas',
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

        validacion_plan = validar_plan_completado_para_examen(matricula)

        if not validacion_plan['completo']:
            return Response(
                {'error': validacion_plan['error']},
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
        ).order_by('?')[:30]

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
        return obtener_foto_instructor(instructor)

    def serializar_instructor(self, request, instructor):
        categoria = instructor.categoria_instructor or ""

        return {
            "id": instructor.id,
            "nombre": instructor.nombre,
            "apellido": instructor.apellido,
            "telefono": instructor.numero_telefono or "",
            "direccion": instructor.direccion or "",
            "edad": instructor.edad,
            "experiencia": instructor.experiencia or "",
            "categoria": categoria,
            "categoria_instructor": categoria,
            "foto": self.get_foto_url(request, instructor),
            "cedula": instructor.cedula or "",
            "nacionalidad": instructor.nacionalidad or "",
            "centro_trabajo": instructor.centro_trabajo or "",
            "cargo": instructor.cargo or "",
        }

    def serializar_estudiante(self, estudiante):
        return {
            "id": estudiante.id,
            "nombre": estudiante.nombre,
            "apellido": estudiante.apellido,
            "cedula": estudiante.cedula,
            "telefono": estudiante.telefono_movil,
            "direccion": estudiante.direccion,
            "edad": estudiante.edad,
            "nivel_educativo": estudiante.nivel_educativo,
            "nacionalidad": estudiante.nacionalidad or "",
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
    fecha_desde = request.query_params.get('desde')
    fecha_hasta = request.query_params.get('hasta')

    ruta_plantilla = os.path.join(
        settings.BASE_DIR,
        'app_escuela',
        'plantilla',
        'INFORME TRANSITO POLICIA NAC.xlsm'
    )

    if not os.path.exists(ruta_plantilla):
        return Response(
            {'error': f'No existe la plantilla: {ruta_plantilla}'},
            status=404
        )

    wb = load_workbook(
        ruta_plantilla,
        keep_vba=True
    )

    def copiar_estilo_fila(ws, fila_origen, fila_destino, columnas):
        for columna in range(1, columnas + 1):
            origen = ws.cell(row=fila_origen, column=columna)
            destino = ws.cell(row=fila_destino, column=columna)

            if type(destino).__name__ == 'MergedCell':
                continue

            if origen.has_style:
                destino._style = copy(origen._style)

            destino.font = copy(origen.font)
            destino.fill = copy(origen.fill)
            destino.border = copy(origen.border)
            destino.alignment = copy(origen.alignment)
            destino.number_format = origen.number_format
            destino.protection = copy(origen.protection)

        ws.row_dimensions[fila_destino].height = ws.row_dimensions[fila_origen].height

    def aplicar_estilo_tabla_manual(ws, fila, columna_inicio, columna_fin, es_par):
        azul = "B8CCE4"
        azul_claro = "DCE6F1"
        blanco = "FFFFFF"

        fill = PatternFill(
            fill_type="solid",
            fgColor=azul if es_par else azul_claro
        )

        borde = Side(style="thin", color="FFFFFF")

        for columna in range(columna_inicio, columna_fin + 1):
            celda = ws.cell(row=fila, column=columna)

            if type(celda).__name__ == "MergedCell":
                continue

            celda.fill = fill
            celda.border = Border(
                left=borde,
                right=borde,
                top=borde,
                bottom=borde
            )
            celda.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True
            )

    nombre_hoja = 'LISTADO INSTRUCTORES'

    if nombre_hoja not in wb.sheetnames:
        return Response(
            {'error': f'No existe la hoja {nombre_hoja}. Hojas disponibles: {wb.sheetnames}'},
            status=400
        )

    ws = wb[nombre_hoja]

    fila_inicio = 5

    fila = fila_inicio

    imagenes_conservar = []
    archivos_temporales = []

    for imagen_excel in ws._images:
        try:
            columna_imagen = imagen_excel.anchor._from.col + 1
            fila_imagen = imagen_excel.anchor._from.row + 1

            if columna_imagen == 2 and fila_imagen >= fila_inicio:
                continue

            imagenes_conservar.append(imagen_excel)

        except Exception:
            imagenes_conservar.append(imagen_excel)

    ws._images = imagenes_conservar

    while fila <= ws.max_row:

        for columna in range(1, 18):
            if columna != 2:
                ws.cell(row=fila, column=columna).value = None

        fila += 1

    instructores = Instructor.objects.order_by(
        'nombre',
        'apellido'
    )

    fila = fila_inicio

    for index, instructor in enumerate(instructores, start=1):
        copiar_estilo_fila(
            ws,
            fila_inicio,
            fila,
            17
        )

        ws.row_dimensions[fila].height = 65

        nombre_completo = (
            f"{instructor.nombre or ''} "
            f"{instructor.apellido or ''}"
        ).strip()

        ws.cell(row=fila, column=1, value=index)

        ruta_foto = obtener_ruta_foto_instructor_para_excel(instructor)

        if ruta_foto:
            archivos_temporales.append(ruta_foto)

            try:
                imagen = ExcelImage(ruta_foto)

                imagen.width = 42
                imagen.height = 42

                ws.row_dimensions[fila].height = 48
                ws.column_dimensions['B'].width = 10

                ws.add_image(imagen, f'B{fila}')

            except Exception:
                pass

        ws.cell(row=fila, column=3, value=nombre_completo)

        ws.cell(
            row=fila,
            column=4,
            value=instructor.cedula or ""
        )

        ws.cell(
            row=fila,
            column=5,
            value=instructor.nacionalidad or ""
        )

        ws.cell(
            row=fila,
            column=6,
            value=instructor.direccion or ""
        )

        ws.cell(
            row=fila,
            column=7,
            value=instructor.numero_telefono or ""
        )

        ws.cell(
            row=fila,
            column=8,
            value=instructor.nivel_escolar or ""
        )

        ws.cell(
            row=fila,
            column=9,
            value=instructor.categoria_instructor or ""
        )

        ws.cell(
            row=fila,
            column=10,
            value=instructor.antecedentes_penales or ""
        )

        ws.cell(
            row=fila,
            column=11,
            value=instructor.centro_trabajo or ""
        )

        ws.cell(
            row=fila,
            column=12,
            value=instructor.cargo or ""
        )

        ws.cell(
            row=fila,
            column=13,
            value=instructor.curso_aprobado_instructor or ""
        )

        ws.cell(
            row=fila,
            column=14,
            value=(
                instructor.fecha_ingreso.strftime('%d/%m/%Y')
                if instructor.fecha_ingreso else ""
            )
        )

        ws.cell(
            row=fila,
            column=15,
            value=(
                instructor.fecha_salida.strftime('%d/%m/%Y')
                if instructor.fecha_salida else ""
            )
        )

        ws.cell(
            row=fila,
            column=16,
            value=instructor.motivo_salida or ""
        )

        ws.cell(
            row=fila,
            column=17,
            value=instructor.infracciones_resoluciones or ""
        )

        fila += 1

    nombre_hoja_ingresos = 'REPORTE DE INGRESOS'

    if nombre_hoja_ingresos not in wb.sheetnames:
        return Response(
            {'error': f'No existe la hoja {nombre_hoja_ingresos}. Hojas disponibles: {wb.sheetnames}'},
            status=400
        )

    ws_ingresos = wb[nombre_hoja_ingresos]

    texto_fecha = ""

    if fecha_desde and fecha_hasta:
        texto_fecha = (
            f"Desde {fecha_desde} hasta {fecha_hasta}"
        )

    elif fecha_desde:
        texto_fecha = (
            f"Desde {fecha_desde}"
        )

    elif fecha_hasta:
        texto_fecha = (
            f"Hasta {fecha_hasta}"
        )

    ws_ingresos.cell(row=3, column=2, value=timezone.now().strftime('%d/%m/%Y'))

    fila_inicio_ingresos = 5
    fila_modelo_ingresos_azul = 5
    fila_modelo_ingresos_clara = 6
    fila = fila_inicio_ingresos

    while fila <= ws_ingresos.max_row:
        for columna in range(1, 16):
            ws_ingresos.cell(row=fila, column=columna).value = None

        fila += 1

    matriculas = Matricula.objects.select_related(
        'estudiante',
        'categoria',
    ).filter(
        estado__in=['matriculado', 'finalizado']
    )

    if fecha_desde:
        matriculas = matriculas.filter(
            fecha_registro__gte=fecha_desde
        )

    if fecha_hasta:
        matriculas = matriculas.filter(
            fecha_registro__lte=fecha_hasta
        )

    matriculas = matriculas.order_by(
        'fecha_registro',
        'id'
    )

    fila = fila_inicio_ingresos

    for matricula in matriculas:
        fila_modelo = (
            fila_modelo_ingresos_azul
            if (fila - fila_inicio_ingresos) % 2 == 0
            else fila_modelo_ingresos_clara
        )

        copiar_estilo_fila(
            ws_ingresos,
            fila_modelo,
            fila,
            15
        )

        aplicar_estilo_tabla_manual(
            ws_ingresos,
            fila,
            1,
            15,
            (fila - fila_inicio_ingresos) % 2 == 0
        )

        estudiante = matricula.estudiante

        fecha_finalizacion = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False
        ).order_by(
            '-fecha'
        ).values_list(
            'fecha',
            flat=True
        ).first()

        if matricula.tipo_curso == "Principiante":
            horas_practicas = 15
        else:
            horas_practicas = matricula.horas_reforzamiento or 0

        horas_totales = round(float(horas_practicas) / 0.6)

        horas_teoricas = round(
            horas_totales - float(horas_practicas)
        )

        ws_ingresos.cell(
            row=fila,
            column=1,
            value=estudiante.codigo_estudiante or ""
        )

        ws_ingresos.cell(
            row=fila,
            column=2,
            value=f"{estudiante.nombre or ''} {estudiante.apellido or ''}".strip()
        )

        ws_ingresos.cell(
            row=fila,
            column=3,
            value=estudiante.nacionalidad or ""
        )

        ws_ingresos.cell(
            row=fila,
            column=4,
            value=estudiante.cedula or ""
        )

        ws_ingresos.cell(
            row=fila,
            column=5,
            value=estudiante.direccion or ""
        )

        ws_ingresos.cell(
            row=fila,
            column=6,
            value=estudiante.telefono_movil or ""
        )

        ws_ingresos.cell(
            row=fila,
            column=7,
            value=estudiante.nivel_educativo or ""
        )

        ws_ingresos.cell(
            row=fila,
            column=8,
            value="X" if matricula.tipo_curso == "Principiante" else ""
        )

        ws_ingresos.cell(
            row=fila,
            column=9,
            value="X" if matricula.tipo_curso == "Intermedio" else ""
        )

        ws_ingresos.cell(
            row=fila,
            column=10,
            value="X" if matricula.tipo_curso == "Avanzado" else ""
        )

        ws_ingresos.cell(
            row=fila,
            column=11,
            value=matricula.categoria.nombre if matricula.categoria else ""
        )

        ws_ingresos.cell(
            row=fila,
            column=12,
            value=matricula.fecha_registro.strftime('%d/%m/%Y') if matricula.fecha_registro else ""
        )

        ws_ingresos.cell(
            row=fila,
            column=13,
            value=fecha_finalizacion.strftime('%d/%m/%Y') if fecha_finalizacion else ""
        )

        ws_ingresos.cell(
            row=fila,
            column=14,
            value=horas_teoricas
        )

        ws_ingresos.cell(
            row=fila,
            column=15,
            value=horas_practicas
        )

        fila += 1

    ultima_fila_ingresos = fila - 1

    nombre_hoja_egresos = 'REPORTE DE EGRESOS'

    if nombre_hoja_egresos not in wb.sheetnames:
        return Response(
            {'error': f'No existe la hoja {nombre_hoja_egresos}. Hojas disponibles: {wb.sheetnames}'},
            status=400
        )

    ws_egresos = wb[nombre_hoja_egresos]

    ws_egresos.cell(
        row=5,
        column=2,
        value=timezone.now().strftime('%d/%m/%Y')
    )

    fila_inicio_egresos = 8
    fila_estilo_egresos = 8
    fila = fila_inicio_egresos

    while fila <= ws_egresos.max_row:
        for columna in range(1, 20):
            ws_egresos.cell(row=fila, column=columna).value = None

        fila += 1

    matriculas_con_teorico = set()
    matriculas_con_practico = set()

    for nota in Notas.objects.all():
        try:
            valor_nota = float(nota.nota)
        except (TypeError, ValueError):
            continue

        tipo_nota = str(nota.tipo_nota or "").strip().lower()

        if tipo_nota == "teorico" and valor_nota >= 80:
            matriculas_con_teorico.add(nota.matricula_id)

        if tipo_nota == "practico" and valor_nota >= 80:
            matriculas_con_practico.add(nota.matricula_id)

    matriculas_egresadas_ids = matriculas_con_teorico.intersection(
        matriculas_con_practico
    )

    egresados = Matricula.objects.select_related(
        'estudiante',
        'categoria',
    ).filter(
        id__in=matriculas_egresadas_ids
    )

    if fecha_desde:
        egresados = egresados.filter(
            fecha_registro__gte=fecha_desde
        )

    if fecha_hasta:
        egresados = egresados.filter(
            fecha_registro__lte=fecha_hasta
        )

    egresados = egresados.order_by(
        'fecha_registro',
        'id'
    )

    fila = fila_inicio_egresos

    for matricula in egresados:
        copiar_estilo_fila(
            ws_egresos,
            fila_estilo_egresos,
            fila,
            20
        )

        aplicar_estilo_tabla_manual(
            ws_egresos,
            fila,
            1,
            20,
            (fila - fila_inicio_egresos) % 2 == 0
        )

        estudiante = matricula.estudiante

        fecha_finalizacion = Calendario.objects.filter(
            matricula=matricula,
            es_examen=False
        ).order_by(
            '-fecha'
        ).values_list(
            'fecha',
            flat=True
        ).first()

        nota_teorica_obj = Notas.objects.filter(
            matricula=matricula,
            tipo_nota='teorico'
        ).first()

        nota_practica_obj = Notas.objects.filter(
            matricula=matricula,
            tipo_nota='practico'
        ).first()

        nota_teorica = nota_teorica_obj.nota if nota_teorica_obj else ""
        nota_practica = nota_practica_obj.nota if nota_practica_obj else ""

        if matricula.tipo_curso == "Principiante":
            horas_practicas = 15
        else:
            horas_practicas = matricula.horas_reforzamiento or 0

        horas_totales = round(float(horas_practicas) / 0.6)
        horas_teoricas = round(
            horas_totales - float(horas_practicas)
        )

        ws_egresos.cell(row=fila, column=1, value="")

        ws_egresos.cell(
            row=fila,
            column=2,
            value=f"{estudiante.nombre or ''} {estudiante.apellido or ''}".strip()
        )

        ws_egresos.cell(
            row=fila,
            column=3,
            value=estudiante.nacionalidad or ""
        )

        ws_egresos.cell(
            row=fila,
            column=4,
            value=estudiante.cedula or ""
        )

        ws_egresos.cell(
            row=fila,
            column=5,
            value=estudiante.telefono_movil or ""
        )

        ws_egresos.cell(
            row=fila,
            column=6,
            value=estudiante.nivel_educativo or ""
        )

        ws_egresos.cell(
            row=fila,
            column=7,
            value="X" if matricula.tipo_curso == "Principiante" else ""
        )

        ws_egresos.cell(
            row=fila,
            column=8,
            value="X" if matricula.tipo_curso == "Intermedio" else ""
        )

        ws_egresos.cell(
            row=fila,
            column=9,
            value="X" if matricula.tipo_curso == "Avanzado" else ""
        )

        ws_egresos.cell(
            row=fila,
            column=10,
            value=str(matricula.categoria) if matricula.categoria else ""
        )

        ws_egresos.cell(
            row=fila,
            column=11,
            value=matricula.fecha_registro.strftime('%d/%m/%Y') if matricula.fecha_registro else ""
        )

        ws_egresos.cell(
            row=fila,
            column=12,
            value=fecha_finalizacion.strftime('%d/%m/%Y') if fecha_finalizacion else ""
        )

        ws_egresos.cell(row=fila, column=13, value=horas_teoricas)
        ws_egresos.cell(row=fila, column=14, value=horas_practicas)
        ws_egresos.cell(row=fila, column=15, value=nota_teorica or "")
        ws_egresos.cell(row=fila, column=16, value=nota_practica or "")

        ws_egresos.cell(row=fila, column=17, value="")
        ws_egresos.cell(row=fila, column=18, value="")
        ws_egresos.cell(row=fila, column=19, value="")

        ws_egresos.cell(row=fila, column=20, value="")

        fila += 1

    ultima_fila_egresos = fila - 1

    response = HttpResponse(
        content_type='application/vnd.ms-excel.sheet.macroEnabled.12'
    )

    response[
        'Content-Disposition'
    ] = 'attachment; filename="INFORME_TRANSITO_POLICIA_NAC.xlsm"'

    try:
        wb.save(response)
    finally:
        for ruta in archivos_temporales:
            try:
                if ruta and os.path.exists(ruta):
                    os.remove(ruta)
            except Exception:
                pass

    return response

class PagoInstructorViewSet(viewsets.ModelViewSet):
    queryset = PagoInstructor.objects.all().order_by('-fecha_inicio')
    serializer_class = PagoInstructorSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        activo = serializer.validated_data.get('activo', True)

        if activo:
            PagoInstructor.objects.filter(activo=True).update(
                activo=False,
                fecha_fin=timezone.now().date()
            )

        serializer.save()

    def perform_update(self, serializer):
        activo = serializer.validated_data.get('activo', None)

        if activo is True:
            PagoInstructor.objects.exclude(
                id=serializer.instance.id
            ).filter(
                activo=True
            ).update(
                activo=False,
                fecha_fin=timezone.now().date()
            )

        serializer.save()


class CargoInstitucionalViewSet(viewsets.ModelViewSet):
    queryset = CargoInstitucional.objects.all().order_by('tipo', 'nombre')
    serializer_class = CargoInstitucionalSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para crear este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para editar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not es_admin(request.user):
            return Response(
                {'error': 'No tienes permiso para eliminar este registro.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().destroy(request, *args, **kwargs)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_induccion_instructores(request):
    fecha_desde = request.query_params.get('desde')
    fecha_hasta = request.query_params.get('hasta')
    instructor_id = request.query_params.get('instructor')

    if not instructor_id:
        return Response(
            {'error': 'Debe seleccionar un instructor.'},
            status=400
        )

    pago_instructor = PagoInstructor.objects.filter(
        activo=True
    ).order_by(
        '-fecha_inicio',
        '-id'
    ).first()

    if not pago_instructor:
        return Response(
            {'error': 'No hay una tarifa activa configurada para el pago por hora del instructor.'},
            status=400
        )

    tarifa_por_hora = pago_instructor.monto_por_alumno

    try:
        instructor = Instructor.objects.get(id=instructor_id)
    except Instructor.DoesNotExist:
        return Response(
            {'error': 'Instructor no encontrado.'},
            status=404
        )

    notas_teoricas = Notas.objects.filter(
        tipo_nota='teorico'
    ).values_list(
        'matricula_id',
        flat=True
    )

    notas_practicas = Notas.objects.filter(
        tipo_nota='practico',
        instructor_id=instructor_id
    ).values_list(
        'matricula_id',
        flat=True
    )

    matriculas_ids = set(notas_teoricas).intersection(
        set(notas_practicas)
    )

    matriculas = Matricula.objects.select_related(
        'estudiante',
        'categoria'
    ).filter(
        id__in=matriculas_ids
    )

    if fecha_desde:
        matriculas = matriculas.filter(
            fecha_registro__gte=fecha_desde
        )

    if fecha_hasta:
        matriculas = matriculas.filter(
            fecha_registro__lte=fecha_hasta
        )

    matriculas = matriculas.order_by(
        'fecha_registro',
        'estudiante__nombre',
        'estudiante__apellido',
        'id'
    )

    datos = []
    total = Decimal('0')

    for matricula in matriculas:
        estudiante = matricula.estudiante

        recibo = Recibo.objects.filter(
            matricula=matricula
        ).order_by(
            '-fecha_pago',
            '-id'
        ).first()

        if matricula.tipo_curso == 'Principiante':
            horas_practicas = Decimal('15')
        else:
            horas_practicas = Decimal(str(matricula.horas_reforzamiento or 0))

        monto = horas_practicas * tarifa_por_hora
        total += monto

        if matricula.tipo_curso in ['Intermedio', 'Avanzado']:
            observacion = f'Reforzamiento {horas_practicas} horas'
        else:
            observacion = 'Curso principiante 15 horas prácticas'

        datos.append({
            'matricula_id': matricula.id,
            'estudiante': f'{estudiante.nombre or ""} {estudiante.apellido or ""}'.strip(),
            'fecha': matricula.fecha_registro.strftime('%d/%m/%Y') if matricula.fecha_registro else '',
            'numero_recibo': recibo.numero_recibo if recibo and recibo.numero_recibo else '',
            'codigo_egreso': matricula.id,
            'horas': float(horas_practicas),
            'tarifa_hora': float(tarifa_por_hora),
            'cobro': float(monto),
            'observaciones': observacion,
        })

    gerente = CargoInstitucional.objects.filter(
        tipo='gerente',
        activo=True
    ).first()

    director = CargoInstitucional.objects.filter(
        tipo='director',
        activo=True
    ).first()

    return Response({
        'instructor': {
            'id': instructor.id,
            'nombre': f'{instructor.nombre or ""} {instructor.apellido or ""}'.strip(),
        },
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_emision': timezone.now().strftime('%d/%m/%Y'),
        'tarifa_hora': float(tarifa_por_hora),
        'total': float(total),
        'estudiantes': datos,
        
        'firmas': {
            'gerente_nombre': gerente.nombre if gerente else '',
            'gerente_cargo': gerente.cargo if gerente else '',
            'director_nombre': director.nombre if director else '',
            'director_cargo': director.cargo if director else '',
        },
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_kilometros_instructor(request):
    fecha_desde = request.query_params.get('desde')
    fecha_hasta = request.query_params.get('hasta')
    instructor_id = request.query_params.get('instructor')

    if not instructor_id:
        return Response(
            {'error': 'Debe seleccionar un instructor.'},
            status=400
        )

    try:
        instructor = Instructor.objects.get(id=instructor_id)
    except Instructor.DoesNotExist:
        return Response(
            {'error': 'Instructor no encontrado.'},
            status=404
        )

    asistencias = Asistencia.objects.select_related(
        'As_estudiante',
        'As_calendario',
        'As_calendario__instructor',
        'As_calendario__matricula',
    ).filter(
        As_calendario__instructor_id=instructor_id,
        estado='asistio',
        km_inicial__isnull=False,
        km_final__isnull=False,
    )

    if fecha_desde:
        asistencias = asistencias.filter(
            As_calendario__fecha__gte=fecha_desde
        )

    if fecha_hasta:
        asistencias = asistencias.filter(
            As_calendario__fecha__lte=fecha_hasta
        )

    asistencias = asistencias.order_by(
        'As_calendario__fecha',
        'As_calendario__hora_inicio',
        'id'
    )

    wb = Workbook()
    ws = wb.active
    ws.title = 'Kilómetros por Instructor'

    thin = Side(style='thin', color='000000')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_fill = PatternFill(fill_type='solid', fgColor='D9EAF7')
    titulo_fill = PatternFill(fill_type='solid', fgColor='FFFFFF')

    ws.merge_cells('A1:J1')
    ws['A1'] = 'Instituto de Formación y Capacitación “Adiact”'
    ws['A1'].font = Font(bold=True, size=16)
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:J2')
    ws['A2'] = 'Somos expertos en Formación y Capacitación del Talento Humano'
    ws['A2'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A3:J3')
    ws['A3'] = 'Ética, Integridad, Dedicación y Solidaridad'
    ws['A3'].font = Font(bold=True)
    ws['A3'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A5:J5')
    ws['A5'] = 'REPORTE DE KILÓMETROS RECORRIDOS POR INSTRUCTOR'
    ws['A5'].font = Font(bold=True, size=14)
    ws['A5'].alignment = Alignment(horizontal='center')
    ws['A5'].fill = titulo_fill

    ws['A7'] = 'Instructor:'
    ws['B7'] = f'{instructor.nombre or ""} {instructor.apellido or ""}'.strip()

    ws['A8'] = 'Fecha de emisión:'
    ws['B8'] = timezone.now().strftime('%d/%m/%Y')

    ws['D8'] = 'Desde:'
    ws['E8'] = fecha_desde or 'Inicio'

    ws['F8'] = 'Hasta:'
    ws['G8'] = fecha_hasta or 'Fin'

    encabezados = [
        'No.',
        'Fecha',
        'Instructor',
        'Estudiante',
        'Cédula',
        'Clase No.',
        'Hora Inicio',
        'Hora Fin',
        'Km Inicial',
        'Km Final',
        'Km Recorridos',
    ]

    fila_encabezado = 10

    for col, encabezado in enumerate(encabezados, start=1):
        celda = ws.cell(row=fila_encabezado, column=col, value=encabezado)
        celda.font = Font(bold=True)
        celda.fill = header_fill
        celda.border = border
        celda.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    fila = fila_encabezado + 1
    total_km = Decimal('0')

    for index, asistencia in enumerate(asistencias, start=1):
        clase = asistencia.As_calendario
        estudiante = asistencia.As_estudiante

        km_inicial = asistencia.km_inicial or Decimal('0')
        km_final = asistencia.km_final or Decimal('0')
        km_recorridos = asistencia.km_recorridos or Decimal('0')

        total_km += km_recorridos

        valores = [
            index,
            clase.fecha.strftime('%d/%m/%Y') if clase.fecha else '',
            f'{instructor.nombre or ""} {instructor.apellido or ""}'.strip(),
            f'{estudiante.nombre or ""} {estudiante.apellido or ""}'.strip(),
            estudiante.cedula or '',
            clase.numero_clase,
            clase.hora_inicio.strftime('%H:%M') if clase.hora_inicio else '',
            clase.hora_fin.strftime('%H:%M') if clase.hora_fin else '',
            float(km_inicial),
            float(km_final),
            float(km_recorridos),
        ]

        for col, valor in enumerate(valores, start=1):
            celda = ws.cell(row=fila, column=col, value=valor)
            celda.border = border
            celda.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        fila += 1

    ws.cell(row=fila, column=10, value='TOTAL KM:')
    ws.cell(row=fila, column=11, value=float(total_km))

    for col in range(10, 12):
        celda = ws.cell(row=fila, column=col)
        celda.font = Font(bold=True)
        celda.border = border
        celda.fill = header_fill
        celda.alignment = Alignment(horizontal='center')

    fila_footer = fila + 3

    ws.merge_cells(start_row=fila_footer, start_column=1, end_row=fila_footer, end_column=12)
    ws.cell(
        row=fila_footer,
        column=1,
        value='Gasolinera Uno Sutiaba 1 cuadra al norte ½ cuadra al oeste. León, Nicaragua'
    )

    ws.merge_cells(start_row=fila_footer + 1, start_column=1, end_row=fila_footer + 1, end_column=12)
    ws.cell(
        row=fila_footer + 1,
        column=1,
        value='Teléfonos: 2311-1333 y 8966-3770. email: institutoadiact@esesa.com.ni'
    )

    ws.cell(row=fila_footer, column=1).alignment = Alignment(horizontal='center')
    ws.cell(row=fila_footer + 1, column=1).alignment = Alignment(horizontal='center')

    columnas = {
        'A': 8,
        'B': 15,
        'C': 28,
        'D': 28,
        'E': 18,
        'F': 12,
        'G': 14,
        'H': 14,
        'I': 14,
        'J': 14,
        'K': 16,
        'L': 28,
    }

    for columna, ancho in columnas.items():
        ws.column_dimensions[columna].width = ancho

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    response['Content-Disposition'] = 'attachment; filename="reporte_kilometros_instructor.xlsx"'

    wb.save(response)

    return response

def certificado_numero(valor):
    try:
        if valor is None or valor == "":
            return None

        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def certificado_fecha_larga(fecha):
    if not fecha:
        return ""

    meses = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }

    return f"{fecha.day:02d} de {meses[fecha.month]} del {fecha.year}"


def certificado_dia_letras(dia):
    dias = {
        1: "un",
        2: "dos",
        3: "tres",
        4: "cuatro",
        5: "cinco",
        6: "seis",
        7: "siete",
        8: "ocho",
        9: "nueve",
        10: "diez",
        11: "once",
        12: "doce",
        13: "trece",
        14: "catorce",
        15: "quince",
        16: "dieciséis",
        17: "diecisiete",
        18: "dieciocho",
        19: "diecinueve",
        20: "veinte",
        21: "veintiún",
        22: "veintidós",
        23: "veintitrés",
        24: "veinticuatro",
        25: "veinticinco",
        26: "veintiséis",
        27: "veintisiete",
        28: "veintiocho",
        29: "veintinueve",
        30: "treinta",
        31: "treinta y un",
    }

    return dias.get(dia, str(dia))


def certificado_mes_anio(fecha):
    if not fecha:
        return ""

    meses = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }

    return f"{meses[fecha.month]} del año {fecha.year}"


def certificado_run(parrafo, texto, size=8, bold=False):
    run = parrafo.add_run(str(texto))
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    return run


def certificado_parrafo(celda, texto="", size=8, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, after=0):
    parrafo = celda.add_paragraph()
    parrafo.alignment = align
    parrafo.paragraph_format.space_before = Pt(0)
    parrafo.paragraph_format.space_after = Pt(after)
    certificado_run(parrafo, texto, size=size, bold=bold)
    return parrafo


def certificado_set_margenes_celda(celda, top=60, start=80, bottom=60, end=80):
    tc = celda._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")

    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)

    valores = {
        "top": top,
        "start": start,
        "bottom": bottom,
        "end": end,
    }

    for nombre, valor in valores.items():
        elemento = tc_mar.find(qn(f"w:{nombre}"))

        if elemento is None:
            elemento = OxmlElement(f"w:{nombre}")
            tc_mar.append(elemento)

        elemento.set(qn("w:w"), str(valor))
        elemento.set(qn("w:type"), "dxa")


def certificado_sombrear_celda(celda, color):
    tc_pr = celda._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))

    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)

    shd.set(qn("w:fill"), color)


def certificado_bordes_tabla(tabla, color="1F4E79", size="14"):
    tbl = tabla._tbl
    tbl_pr = tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")

    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)

    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        tag = qn(f"w:{edge}")
        element = borders.find(tag)

        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)

        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def certificado_sin_bordes_tabla(tabla):
    tbl = tabla._tbl
    tbl_pr = tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")

    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)

    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        tag = qn(f"w:{edge}")
        element = borders.find(tag)

        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)

        element.set(qn("w:val"), "nil")


def certificado_agregar_imagen(celda, ruta, ancho):
    if not os.path.exists(ruta):
        return False

    parrafo = celda.paragraphs[0]
    parrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = parrafo.add_run()
    run.add_picture(ruta, width=Inches(ancho))

    return True


def certificado_obtener_datos(desde, hasta):
    desde_fecha = parse_date(desde)
    hasta_fecha = parse_date(hasta)

    if not desde_fecha or not hasta_fecha:
        return []

    resultados = []

    matriculas = Matricula.objects.select_related(
        "estudiante",
        "categoria",
        "plan_de_estudio",
    ).filter(
        tipo_curso="Principiante",
    ).order_by(
        "estudiante__apellido",
        "estudiante__nombre",
    )

    for matricula in matriculas:
        nota_teorica_obj = Notas.objects.filter(
            matricula=matricula,
            tipo_nota="teorico",
        ).order_by("-fecha_registro", "-id").first()

        nota_practica_obj = Notas.objects.filter(
            matricula=matricula,
            tipo_nota="practico",
        ).order_by("-fecha_registro", "-id").first()

        if not nota_teorica_obj or not nota_practica_obj:
            continue

        nota_teorica = certificado_numero(nota_teorica_obj.nota)
        nota_practica = certificado_numero(nota_practica_obj.nota)

        if nota_teorica is None or nota_practica is None:
            continue

        if nota_teorica < Decimal("80") or nota_practica < Decimal("80"):
            continue

        fecha_teorica = None
        fecha_practica = None

        if getattr(nota_teorica_obj, "fecha_registro", None):
            fecha_teorica = nota_teorica_obj.fecha_registro.date()

        if getattr(nota_practica_obj, "fecha_registro", None):
            fecha_practica = nota_practica_obj.fecha_registro.date()

        fechas_notas = [
            fecha for fecha in [fecha_teorica, fecha_practica]
            if fecha is not None
        ]

        if fechas_notas:
            fecha_egreso = max(fechas_notas)
        elif matricula.fecha_registro:
            fecha_egreso = matricula.fecha_registro.date()
        else:
            continue

        if fecha_egreso < desde_fecha or fecha_egreso > hasta_fecha:
            continue

        estudiante = matricula.estudiante
        categoria = matricula.categoria.nombre if matricula.categoria else ""

        fecha_inicio = matricula.fecha_registro.date() if matricula.fecha_registro else None

        resultados.append({
            "id": matricula.id,
            "estudiante": f"{estudiante.nombre} {estudiante.apellido}".strip().upper(),
            "cedula": estudiante.cedula,
            "categoria": categoria,
            "tipo_curso": matricula.tipo_curso,
            "fecha_inicio": fecha_inicio,
            "fecha_egreso": fecha_egreso,
            "nota_teorica": nota_teorica,
            "nota_practica": nota_practica,
        })

    return resultados


def certificado_crear_en_celda(celda, item, logo_path, auto_path, fecha_emision):
    celda._tc.clear_content()
    celda.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    certificado_set_margenes_celda(celda, top=40, start=70, bottom=40, end=70)
    certificado_sombrear_celda(celda, "E1A13A")

    tabla_marco = celda.add_table(rows=1, cols=1)
    tabla_marco.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabla_marco.autofit = True
    certificado_bordes_tabla(tabla_marco, color="E1A13A", size="8")

    marco = tabla_marco.cell(0, 0)
    marco.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    certificado_sombrear_celda(marco, "FFFFFF")
    certificado_set_margenes_celda(marco, top=55, start=65, bottom=55, end=65)

    tabla_interna = marco.add_table(rows=1, cols=1)
    tabla_interna.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabla_interna.autofit = True
    certificado_bordes_tabla(tabla_interna, color="1F4E79", size="16")

    contenido = tabla_interna.cell(0, 0)
    contenido.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    certificado_sombrear_celda(contenido, "FFFFFF")
    certificado_set_margenes_celda(contenido, top=45, start=80, bottom=45, end=80)

    header = contenido.add_table(rows=2, cols=3)
    header.alignment = WD_TABLE_ALIGNMENT.CENTER
    header.autofit = True
    certificado_sin_bordes_tabla(header)

    titulo_cell = header.cell(0, 0).merge(header.cell(0, 2))
    certificado_set_margenes_celda(titulo_cell, top=0, start=5, bottom=5, end=5)

    p_titulo = titulo_cell.paragraphs[0]
    p_titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_titulo.paragraph_format.space_after = Pt(0)
    certificado_run(p_titulo, "-ESCUELA DE MANEJO EL CACIQUE ADIACT", size=13, bold=True)

    logo_cell = header.cell(1, 0)
    texto_cell = header.cell(1, 1)
    auto_cell = header.cell(1, 2)

    for celda_header in [logo_cell, texto_cell, auto_cell]:
        certificado_sombrear_celda(celda_header, "E1A13A")
        certificado_set_margenes_celda(celda_header, top=10, start=10, bottom=10, end=10)

    certificado_agregar_imagen(logo_cell, logo_path, 0.60)

    texto_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    texto_cell.paragraphs[0].paragraph_format.space_after = Pt(0)
    certificado_run(texto_cell.paragraphs[0], "CERTIFICA QUE:", size=12, bold=True)

    certificado_agregar_imagen(auto_cell, auto_path, 0.95)

    certificado_parrafo(
        contenido,
        item["estudiante"],
        size=12,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    certificado_parrafo(
        contenido,
        f"Cédula: {item['cedula']}.",
        size=9,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    periodo = ""
    if item["fecha_inicio"] and item["fecha_egreso"]:
        periodo = (
            f"del {certificado_fecha_larga(item['fecha_inicio'])} "
            f"al {certificado_fecha_larga(item['fecha_egreso'])}"
        )
    elif item["fecha_egreso"]:
        periodo = f"hasta el {certificado_fecha_larga(item['fecha_egreso'])}"

    p_texto = contenido.add_paragraph()
    p_texto.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_texto.paragraph_format.space_before = Pt(2)
    p_texto.paragraph_format.space_after = Pt(0)

    certificado_run(
        p_texto,
        "Ha cumplido con el plan de instrucción teórico y práctico aprobado por la DSTN, "
        "de principiante, para optar a la Licencia de Conducir de Tipo Ordinaria en la Categoría ",
        size=8.3,
        bold=True,
    )

    certificado_run(
        p_texto,
        item["categoria"] or "__________",
        size=8.3,
        bold=True,
    )

    certificado_run(
        p_texto,
        f" impartido en el periodo comprendido {periodo}, habiendo obtenido las siguientes calificaciones:",
        size=8.3,
        bold=True,
    )

    certificado_parrafo(
        contenido,
        f"Evaluación Teórica: {int(item['nota_teorica'])} puntos.",
        size=8.8,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    certificado_parrafo(
        contenido,
        f"Evaluación Práctica: {int(item['nota_practica'])} puntos.",
        size=8.8,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    certificado_parrafo(
        contenido,
        "Registrado en el Asiento No. __________ del Folio No. __________ del Tomo No. __________.",
        size=8.2,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    texto_dia = certificado_dia_letras(fecha_emision.day)
    texto_mes = certificado_mes_anio(fecha_emision)

    certificado_parrafo(
        contenido,
        f"Dado en la ciudad de León a los {texto_dia} días del mes de {texto_mes}.",
        size=8.2,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    tabla_firma = contenido.add_table(rows=1, cols=3)
    tabla_firma.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabla_firma.autofit = True
    certificado_sin_bordes_tabla(tabla_firma)

    firma_cell = tabla_firma.cell(0, 1)
    certificado_set_margenes_celda(firma_cell, top=5, start=5, bottom=0, end=5)

    certificado_parrafo(
        firma_cell,
        "______________________________",
        size=7.3,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    certificado_parrafo(
        firma_cell,
        "LIC. FRANCISCO AGUILERA FERRUFINO.",
        size=7.3,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )

    certificado_parrafo(
        firma_cell,
        "Director.",
        size=7.3,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=0,
    )


def certificado_crear_word(certificados, fecha_emision):
    documento = Document()

    section = documento.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.25)
    section.bottom_margin = Inches(0.25)
    section.left_margin = Inches(0.25)
    section.right_margin = Inches(0.25)

    logo_path = os.path.join(settings.BASE_DIR, "static", "certificados", "logo.png")
    auto_path = os.path.join(settings.BASE_DIR, "static", "certificados", "auto.png")

    if not os.path.exists(logo_path):
        raise FileNotFoundError(f"No se encontró el logo en: {logo_path}")

    if not os.path.exists(auto_path):
        raise FileNotFoundError(f"No se encontró la imagen del auto en: {auto_path}")

    for index in range(0, len(certificados), 2):
        grupo = certificados[index:index + 2]

        tabla = documento.add_table(rows=2, cols=1)
        tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
        tabla.autofit = True
        certificado_sin_bordes_tabla(tabla)

        for fila_index in range(2):
            fila = tabla.rows[fila_index]
            fila.height = Inches(5.25)
            fila.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY

            celda = fila.cells[0]
            celda.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

            if fila_index < len(grupo):
                certificado_crear_en_celda(
                    celda,
                    grupo[fila_index],
                    logo_path,
                    auto_path,
                    fecha_emision,
                )
            else:
                celda._tc.clear_content()

        if index + 2 < len(certificados):
            documento.add_page_break()

    return documento


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def certificados_egresados(request):
    if not es_admin(request.user):
        return Response(
            {"detail": "No tienes permiso para consultar certificados."},
            status=403,
        )

    desde = request.GET.get("desde")
    hasta = request.GET.get("hasta")

    if not desde or not hasta:
        return Response(
            {"detail": "Debe enviar fecha desde y fecha hasta."},
            status=400,
        )

    certificados = certificado_obtener_datos(desde, hasta)

    data = []

    for item in certificados:
        data.append({
            "id": item["id"],
            "estudiante": item["estudiante"],
            "cedula": item["cedula"],
            "categoria": item["categoria"],
            "tipo_curso": item["tipo_curso"],
            "fecha_inicio": item["fecha_inicio"].isoformat() if item["fecha_inicio"] else "",
            "fecha_egreso": item["fecha_egreso"].isoformat() if item["fecha_egreso"] else "",
            "nota_teorica": int(item["nota_teorica"]),
            "nota_practica": int(item["nota_practica"]),
        })

    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def certificados_egresados_word(request):
    if not es_admin(request.user):
        return Response(
            {"detail": "No tienes permiso para generar certificados."},
            status=403,
        )

    desde = request.GET.get("desde")
    hasta = request.GET.get("hasta")

    if not desde or not hasta:
        return Response(
            {"detail": "Debe enviar fecha desde y fecha hasta."},
            status=400,
        )

    certificados = certificado_obtener_datos(desde, hasta)

    if not certificados:
        return Response(
            {
                "detail": (
                    "No hay estudiantes egresados del curso principiante con nota teórica "
                    "y práctica mayor o igual a 80 en ese rango de fechas."
                )
            },
            status=404,
        )

    fecha_emision = parse_date(hasta) or timezone.localdate()

    try:
        documento = certificado_crear_word(certificados, fecha_emision)
    except FileNotFoundError as error:
        return Response(
            {"detail": str(error)},
            status=500,
        )

    archivo = BytesIO()
    documento.save(archivo)
    archivo.seek(0)

    response = HttpResponse(
        archivo.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="certificados_{desde}_{hasta}.docx"'
    )

    return response