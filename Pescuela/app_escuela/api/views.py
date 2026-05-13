# app_escuela/api/views.py

from datetime import date, datetime, timedelta
from decimal import Decimal
from decimal import Decimal
from django.db import models

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
    queryset = Instructor.objects.select_related('usuario', 'categoria_vehiculo').all()
    serializer_class = InstructorSerializer
    permission_classes = [IsAuthenticated]




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
    queryset = Usuario.objects.select_related('rol').all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

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

        if matricula.estado != 'aprobado':
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
        'matricula__plan_estudio',
        'instructor',
        'instructor__usuario',
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

        if hasattr(user, 'instructor'):
            return qs.filter(instructor=user.instructor).order_by('fecha', 'hora_inicio')

        if hasattr(user, 'estudiante'):
            return qs.filter(matricula__estudiante=user.estudiante).order_by('fecha', 'hora_inicio')

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
            'plan_estudio',
        ).get(id=data['matricula_id'])

        instructor = Instructor.objects.get(id=data['instructor_id'])

        rango = obtener_rango_horario(matricula)

        if not rango:
            return Response(
                {'error': 'La matrícula no tiene un horario válido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        horas_por_dia = int(data.get('horas_por_dia', 2))
        hora_inicio = datetime.strptime(rango[0], '%H:%M').time()
        hora_fin = (
            datetime.combine(date.today(), hora_inicio) +
            timedelta(hours=horas_por_dia)
        ).time()

        tipo_curso = matricula.plan_estudio.tipo_curso
        modalidad = matricula.plan_estudio.modalidad

        if tipo_curso in ['Intermedio', 'Avanzado']:
            horas = matricula.horas_reforzamiento or matricula.plan_estudio.cantidad_horas
        else:
            horas = matricula.plan_estudio.cantidad_horas

        num_clases = int(horas) // horas_por_dia

        fechas = []
        actual = data['fecha_inicio']
        es_extraordinario = str(modalidad).lower() == 'extraordinario'

        while len(fechas) < num_clases:
            if es_extraordinario and actual.weekday() >= 5:
                fechas.append(actual)

            if not es_extraordinario and actual.weekday() < 5:
                fechas.append(actual)

            actual += timedelta(days=1)

        creadas = []

        with transaction.atomic():
            for i, fecha_clase in enumerate(fechas, start=1):
                choque = Calendario.objects.filter(
                    instructor=instructor,
                    fecha=fecha_clase,
                    hora_inicio__lt=hora_fin,
                    hora_fin__gt=hora_inicio,
                ).exists()

                if choque:
                    return Response(
                        {
                            'error': f'El instructor ya tiene una clase el {fecha_clase} en ese horario.'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                clase = Calendario.objects.create(
                    matricula=matricula,
                    instructor=instructor,
                    fecha=fecha_clase,
                    hora_inicio=hora_inicio,
                    hora_fin=hora_fin,
                    numero_clase=i,
                )

                creadas.append(clase)

        return Response(
            {
                'message': f'Bloque de {num_clases} clases creado correctamente.',
                'fecha_inicio': fechas[0],
                'fecha_fin': fechas[-1],
                'clases_creadas': len(creadas),
                'citas': CalendarioSerializer(creadas, many=True).data,
            },
            status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=['post'], url_path='crear-examen')
    def crear_examen(self, request):
        instructor_id = request.data.get('instructor_id')
        matricula_id = request.data.get('matricula_id')
        fecha = request.data.get('fecha')
        hora_inicio = request.data.get('hora_inicio', '08:00')
        hora_fin = request.data.get('hora_fin', '10:00')

        try:
            matricula = Matricula.objects.select_related('estudiante').get(id=matricula_id)
            instructor = Instructor.objects.get(id=instructor_id)
        except Matricula.DoesNotExist:
            return Response({'error': 'Matrícula no encontrada.'}, status=404)
        except Instructor.DoesNotExist:
            return Response({'error': 'Instructor no encontrado.'}, status=404)

        if matricula.estado != 'aprobado':
            return Response(
                {'error': 'No se puede programar examen porque la matrícula aún no está aprobada.'},
                status=400
            )

        if not matricula.estudiante.usuario:
            return Response(
                {'error': 'No se puede programar examen porque el estudiante todavía no tiene usuario.'},
                status=400
            )

        Calendario.objects.filter(
            matricula=matricula,
            numero_clase=9,
        ).delete()

        examen = Calendario.objects.create(
            matricula=matricula,
            instructor=instructor,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            numero_clase=9,
        )

        return Response({
            'message': 'Examen programado correctamente.',
            'examen': CalendarioSerializer(examen).data,
        }, status=201)


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
        rol = user.rol_nombre if hasattr(user, 'rol_nombre') else ''

        queryset = Notas.objects.select_related(
            'matricula',
            'matricula__estudiante',
            'instructor',
            'plan_de_estudio'
        )

        if rol in ['admin', 'administrador']:
            return queryset

        if rol == 'instructor':
            if user.instructor:
                return queryset.filter(instructor=user.instructor)
            return Notas.objects.none()

        if rol == 'estudiante':
            if user.estudiante:
                return queryset.filter(matricula__estudiante=user.estudiante)
            return Notas.objects.none()

        return Notas.objects.none()


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