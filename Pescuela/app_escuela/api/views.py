# app_escuela/api/views.py

from datetime import date, datetime, timedelta
from decimal import Decimal
from decimal import Decimal
from django.db import models
<<<<<<< Updated upstream
from rest_framework.parsers import MultiPartParser, FormParser
=======
from rest_framework import serializers

>>>>>>> Stashed changes
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

<<<<<<< Updated upstream
=======



>>>>>>> Stashed changes
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
    MatriculaSerializer,
    ReciboSerializer,
    CalendarioSerializer,
    CrearBloqueCitasSerializer,
    AsistenciaSerializer,
    NotasSerializer,
    ValorCursoSerializer,
)

from .serializers import (
     PlanEstudioSerializer, ProgresoTemaSerializer, 
     NotificacionSerializer
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
    queryset = Instructor.objects.select_related('categoria_vehiculo').all()
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

        matriculas = Matricula.objects.select_related(
            'estudiante'
        ).filter(
            estado='matriculado'
        )

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
        matricula = serializer.validated_data.get('matricula')

        if not user.instructor:
            raise serializers.ValidationError({
                'instructor': 'El usuario actual no tiene instructor asignado.'
            })

        plan = PlanEstudio.objects.filter(
            estudiante=matricula.estudiante,
            completado=True
        ).first()

        if not plan:
            raise serializers.ValidationError({
                'plan_de_estudio':
                    'No se puede registrar la nota práctica porque el estudiante aún no ha completado el plan de estudio.'
            })

        serializer.save(
            instructor=user.instructor,
            plan_de_estudio=plan
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
    
# views.py

from django.utils import timezone
from ..models import ProgresoTema, Notificacion, HistorialPlanEstudio

class ProgresoTemaViewSet(viewsets.ModelViewSet):
    queryset = ProgresoTema.objects.select_related(
        'matricula',
        'matricula__estudiante',
        'subtema',
        'subtema__tema',
        'subtema__tema__plan_estudio'
    ).all()

    serializer_class = ProgresoTemaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        queryset = self.queryset

        if rol in ['admin', 'administrador']:
            return queryset

        if rol == 'estudiante' and user.estudiante:
            return queryset.filter(
                matricula__estudiante=user.estudiante
            )

        if rol == 'instructor' and user.instructor:
            return queryset.filter(
                matricula__clases__instructor=user.instructor
            ).distinct()

        return ProgresoTema.objects.none()



    @action(detail=True, methods=['post'], url_path='marcar-estudiante')
    def marcar_estudiante(self, request, pk=None):
        """Estudiante marca que ya estudió el tema"""
        try:
            progreso = self.get_object()
            
            if progreso.estudiante_completado:
                return Response({
                    'success': False,
                    'error': 'Ya habías marcado este tema como estudiado'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                progreso.estudiante_completado = True
                progreso.fecha_estudiante = timezone.now()
                progreso.save()
                
                if progreso.instructor_completado:
                    mensaje = "¡Excelente! Tema completado."
                else:
                    mensaje = "Tema marcado como estudiado. Espera al instructor."
            
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
        """Instructor marca que ya dio la clase"""
        try:
            progreso = self.get_object()
            
            if progreso.instructor_completado:
                return Response({
                    'success': False,
                    'error': 'Ya habías marcado esta clase como dada'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                progreso.instructor_completado = True
                progreso.fecha_instructor = timezone.now()
                progreso.save()
                
                if progreso.estudiante_completado:
                    mensaje = "¡Perfecto! Tema completado."
                else:
                    mensaje = "Clase marcada. Espera al estudiante."
            
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
        

    def _desbloquear_siguiente(self, progreso_actual):
        progresos = list(
            ProgresoTema.objects.filter(
                matricula=progreso_actual.matricula
            ).select_related(
                'subtema',
                'subtema__tema'
            ).order_by(
                'subtema__tema__orden',
                'subtema__orden'
            )
        )

        for index, progreso in enumerate(progresos):
            if progreso.id == progreso_actual.id:
                if index + 1 < len(progresos):
                    siguiente = progresos[index + 1]

                    if not siguiente.desbloqueado:
                        siguiente.desbloqueado = True
                        siguiente.save()

                break
        
    def _verificar_siguiente_tema(self, progreso_actual):
        """Método interno para verificar si puede pasar al siguiente tema"""
        estudiante = progreso_actual.estudiante
        tema_actual = progreso_actual.tema
        plan = tema_actual.plan_estudio
        
        # Obtener todos los temas del plan en orden
        temas_plan = list(plan.temas.all().order_by('orden'))
        
        # Encontrar el índice del tema actual
        try:
            indice_actual = temas_plan.index(tema_actual)
        except ValueError:
            return
        
        # Verificar si hay un siguiente tema
        if indice_actual + 1 < len(temas_plan):
            siguiente_tema = temas_plan[indice_actual + 1]
            
            # Crear progreso para el siguiente tema si no existe
            siguiente_progreso, creado = ProgresoTema.objects.get_or_create(
                estudiante=estudiante,
                tema=siguiente_tema,
                defaults={
                    'estudiante_completado': False,
                    'instructor_completado': False
                }
            )
            
            if creado:
                print(f"Nuevo tema disponible para {estudiante.username}: {siguiente_tema.titulo}")
        
        # Verificar si completó TODO el plan
        self._verificar_plan_completado(estudiante, plan)
    
    def _verificar_plan_completado(self, estudiante, plan):
        """Método interno para verificar si completó todo el plan"""
        todos_temas = plan.temas.all()
        progresos = ProgresoTema.objects.filter(
            estudiante=estudiante,
            tema__in=todos_temas
        )
        
        # Contar cuántos temas tienen ambos checks completados
        completados = progresos.filter(
            estudiante_completado=True,
            instructor_completado=True
        ).count()
        
        total_temas = todos_temas.count()
        
        if completados == total_temas and total_temas > 0:
            # Verificar si ya notificamos antes
            notificacion_existe = Notificacion.objects.filter(
                estudiante=estudiante,
                tipo='plan_completado',
                leida=False
            ).exists()
            
            if not notificacion_existe:
                Notificacion.objects.create(
                    estudiante=estudiante,
                    tema=None,
                    tipo='plan_completado',
                    mensaje=f"🎉 ¡{estudiante.username} ha completado el plan de estudio {plan.nombre}! Ya puede presentar el examen práctico.",
                    leida=False
                )
    
    @action(detail=True, methods=['post'], url_path='admin-forzar')
    def admin_forzar(self, request, pk=None):
        """Administrador fuerza el check de estudiante o instructor"""
        # Verificar que sea admin
        if not request.user.is_staff:
            return Response({
                'success': False,
                'error': 'Solo administradores pueden realizar esta acción'
            }, status=status.HTTP_403_FORBIDDEN)
        
        progreso = self.get_object()
        tipo_check = request.data.get('tipo')  # 'estudiante' o 'instructor'
        valor = request.data.get('valor')  # True o False
        
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
            # Guardar valores anteriores
            old_estudiante = progreso.estudiante_completado
            old_instructor = progreso.instructor_completado
            
            # Actualizar según el tipo
            if tipo_check == 'estudiante':
                progreso.estudiante_completado = valor
            else:
                progreso.instructor_completado = valor
            
            progreso.fecha_admin_edit = timezone.now()
            progreso.save()
            
            # Registrar en historial
            HistorialPlanEstudio.objects.create(
                progreso_tema=progreso,
                usuario=request.user,
                accion='admin_forzar',
                valor_anterior_estudiante=old_estudiante,
                valor_anterior_instructor=old_instructor,
                valor_nuevo_estudiante=progreso.estudiante_completado,
                valor_nuevo_instructor=progreso.instructor_completado
            )
            
            # Crear notificación de intervención
            check_nombre = "estudiante" if tipo_check == 'estudiante' else "instructor"
            accion_texto = "habilitado" if valor else "deshabilitado"
            
            Notificacion.objects.create(
                estudiante=progreso.estudiante,
                tema=progreso.tema,
                tipo='intervencion_admin',
                mensaje=f"El administrador {request.user.username} ha {accion_texto} el check de {check_nombre} para el tema '{progreso.tema.titulo}'.",
                leida=False
            )
            
            # Verificar si ahora ambos checks están completos
            if progreso.estudiante_completado and progreso.instructor_completado:
                self._verificar_siguiente_tema(progreso)
        
        serializer = self.get_serializer(progreso)
        return Response({
            'success': True,
            'message': f'Check de {check_nombre} actualizado exitosamente',
            'data': serializer.data
        })


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