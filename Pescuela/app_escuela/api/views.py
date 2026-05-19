# app_escuela/api/views.py

from datetime import date, datetime, timedelta
from decimal import Decimal
from decimal import Decimal
from django.db import models
from rest_framework.parsers import MultiPartParser, FormParser
import openpyxl
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import HttpResponse
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
)

from .serializers import (
    RolSerializer,
    UserSerializer,
    EstudianteSerializer,
    InstructorSerializer,
    CategoriaVehiculoSerializer,
    PlanEstudioSerializer,
    MatriculaSerializer,
    ReciboSerializer,
    CalendarioSerializer,
    CrearBloqueCitasSerializer,
    AsistenciaSerializer,
    NotasSerializer,
    ValorCursoSerializer,
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
    queryset = PlanEstudio.objects.all()
    serializer_class = PlanEstudioSerializer
    permission_classes = [IsAuthenticated]

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
                'en_caso_de_emergencia': estudiante.en_caso_de_emergencia,
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
    queryset = Notas.objects.all()
    serializer_class = NotasSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = Notas.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'instructor',
        ).all()

        rol = user.rol.nombre.lower() if user.rol else ""

        if rol == 'admin':
            return queryset

        if rol == 'instructor' and user.instructor_id:
            return queryset.filter(instructor_id=user.instructor_id)

        if rol == 'estudiante' and user.estudiante_id:
            return queryset.filter(matricula__estudiante_id=user.estudiante_id)

        return queryset.none()

    def perform_create(self, serializer):
        user = self.request.user
        rol = user.rol.nombre.lower() if user.rol else ""

        if rol != 'instructor':
            raise serializer.ValidationError(
                'Solo el instructor puede registrar notas.'
            )

        if not user.instructor_id:
            raise serializer.ValidationError(
                'Este usuario instructor no tiene un instructor relacionado.'
            )

        serializer.save(
            instructor=user.instructor,
            tipo_nota='practico'
        )



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