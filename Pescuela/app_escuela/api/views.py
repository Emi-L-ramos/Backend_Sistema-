# app_escuela/api/views.py
from datetime import timedelta, date, datetime
import openpyxl
from django.db.models import Sum
from django.http import HttpResponse
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status

# Decoradores y permisos
from rest_framework import permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny

# Respuestas y autenticación
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate

# Excepciones y filtros
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend

# ViewSets
from rest_framework import viewsets

# Modelos
from ..models import Matricula, Recibo, Usuario, Calendario, Notas, Instructor

from django.db import transaction

# Serializers
from .serializers import (
    MatriculaSerializer,
    ReciboSerializer,
    UserSerializer,
    ReporteExcelSerializer,
    CalendarioSerializer,
    CrearBloqueCitasSerializer,
    InstructorSerializer,
)


class InstructorViewSet(viewsets.ModelViewSet):
    queryset = Instructor.objects.all()
    serializer_class = InstructorSerializer
    permission_classes = [IsAuthenticated]


# VIEWSETS
class MatriculaViewSet(viewsets.ModelViewSet):
    queryset = Matricula.objects.all()
    serializer_class = MatriculaSerializer
    permission_classes = [IsAuthenticated]


class ReciboViewSet(viewsets.ModelViewSet):
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except DjangoValidationError as e:
            return Response(
                {"error": e.messages[0] if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except DjangoValidationError as e:
            return Response(
                {"error": e.messages[0] if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]


# LOGIN
@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)

    if user:
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'rol': user.rol,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        })

    return Response({'error': 'Credenciales inválidas'}, status=401)


# EXPORTAR EXCEL
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exportar_egresados_excel(request):
    """
    Genera reporte Excel basado en la fecha de finalización del calendario
    """
    mes = request.query_params.get('mes')
    anio = request.query_params.get('anio')

    if not mes or not anio:
        return Response(
            {"error": "Se requieren los parámetros 'mes' y 'anio'"},
            status=400,
        )

    egresados = Matricula.objects.filter(
        calendario__fecha_fin__month=mes,
        calendario__fecha_fin__year=anio,
    ).select_related('calendario', 'notas')

    if not egresados.exists():
        return Response(
            {"error": "No hay egresados para la fecha seleccionada"},
            status=404,
        )

    serializer = ReporteExcelSerializer(egresados, many=True)
    data = serializer.data

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Egresados_{mes}_{anio}"

    headers = [
        'Nombre', 'Apellido', 'Nacionalidad', 'Cédula', 'Teléfono',
        'Nivel Escolar', 'Tipo de Curso', 'Categoría',
        'Fecha Inicio Matrícula', 'Fecha Finalización',
        'Calificación Práctica', 'Calificación Teórica',
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.font = openpyxl.styles.Font(bold=True)

    for row_num, entry in enumerate(data, 2):
        ws.cell(row=row_num, column=1).value = entry.get('nombre')
        ws.cell(row=row_num, column=2).value = entry.get('apellido')
        ws.cell(row=row_num, column=3).value = entry.get('nacionalidad')
        ws.cell(row=row_num, column=4).value = entry.get('n_documento')
        ws.cell(row=row_num, column=5).value = entry.get('telefonia')
        ws.cell(row=row_num, column=6).value = entry.get('nivel_escolar')
        ws.cell(row=row_num, column=7).value = entry.get('tipo_de_curso')
        ws.cell(row=row_num, column=8).value = entry.get('tipo_categoria')
        ws.cell(row=row_num, column=9).value = entry.get('fecha_inicio')
        ws.cell(row=row_num, column=10).value = entry.get('fecha_finalizacion')
        ws.cell(row=row_num, column=11).value = entry.get('calificacion_p')
        ws.cell(row=row_num, column=12).value = entry.get('calificacion_t')

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 20

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="Reporte_Egresados_{mes}_{anio}.xlsx"'
    )

    wb.save(response)
    return response


# SALDO DE MATRÍCULA
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def saldo(request):
    matricula_id = request.query_params.get('matricula')

    if not matricula_id:
        return Response(
            {"error": "Se requiere el ID de la matrícula"},
            status=400,
        )

    try:
        matricula = Matricula.objects.get(id=matricula_id)
        recibos = matricula.recibos.all()
        tipo_matricula = str(matricula.tipo_curso).lower()

        if 'reforz' in tipo_matricula:
            tipo_curso = 'reforzamiento'
            primer_recibo = recibos.first()
            if primer_recibo and primer_recibo.horas_reforzamiento:
                horas = int(primer_recibo.horas_reforzamiento)
            else:
                horas = int(request.query_params.get('horas', 1))
            horas = max(1, min(horas, 15))
            monto_total = horas * 433.33
        else:
            tipo_curso = 'regular'
            horas = 15
            monto_total = 6500

        total_pagado = float(
            matricula.recibos.aggregate(total=Sum('monto_pagado'))['total'] or 0
        )
        saldo_pendiente = max(monto_total - total_pagado, 0)

        return Response({
            "monto_total": monto_total,
            "total_pagado": total_pagado,
            "saldo_pendiente": saldo_pendiente,
            "cantidad_pagos": recibos.count(),
            "pagos_permitidos": 2,
            "nombre": matricula.nombre,
            "apellido": matricula.apellido,
            "cedula": matricula.cedula,
            "tipo_curso": tipo_curso,
            "horas": horas,
            "precio_hora_reforzamiento": 433.33,
        })

    except Matricula.DoesNotExist:
        return Response(
            {"error": "Matrícula no encontrada"},
            status=404,
        )


# CALENDARIO
class CalendarioViewSet(viewsets.ModelViewSet):
    queryset = Calendario.objects.all()
    serializer_class = CalendarioSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['instructor', 'fecha']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Calendario.objects.select_related('instructor', 'matricula').all()

        mes = self.request.query_params.get('mes')
        if mes:
            try:
                anio, m = map(int, mes.split('-'))
                inicio = date(anio, m, 1)
                fin = date(anio + 1, 1, 1) if m == 12 else date(anio, m + 1, 1)
                qs = qs.filter(fecha__gte=inicio, fecha__lt=fin)
            except (ValueError, TypeError):
                pass

        # Filtro por instructor (compatible con dropdown del frontend)
        instructor_param = self.request.query_params.get('instructor')
        if instructor_param and instructor_param != 'all':
            qs = qs.filter(instructor_id=instructor_param)

        if user.is_authenticated and (user.is_superuser or getattr(user, 'rol', None) == 'admin'):
            return qs.order_by('fecha', 'hora_inicio')

        if hasattr(user, 'instructor'):
            return qs.filter(instructor=user.instructor).order_by('fecha', 'hora_inicio')

        return qs.none()

    @action(detail=False, methods=['get'], url_path='hoy')
    def citas_hoy(self, request):
        """Retorna las citas programadas para hoy"""
        hoy = date.today()
        citas = Calendario.objects.filter(fecha=hoy)

        # Filtrar por instructor si es necesario
        if hasattr(request.user, 'instructor'):
            citas = citas.filter(instructor=request.user.instructor)

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

        try:
            matricula = Matricula.objects.get(pk=data['matricula_id'])
        except Matricula.DoesNotExist:
            return Response({"error": "Matrícula no existe"}, status=400)

        # Obtener el horario de la matrícula
        from datetime import datetime, timedelta

        horas_por_dia = int(data.get('horas_por_dia', 2))
        rango = matricula.obtener_rango_horario()
        if not rango:
            return Response(
                {"error": "La matrícula no tiene un horario válido"},
                status=400,
            )
        hora_inicio = rango[0]
        hora_fin = (datetime.combine(datetime.today(), hora_inicio) + timedelta(hours=horas_por_dia)).time()
        es_extraordinario = (str(matricula.modalidad).lower() == 'extraordinario')
        es_reforzamiento = 'reforz' in str(matricula.tipo_curso).lower()

        if es_reforzamiento:
            horas = int(matricula.horas_reforzamiento) if matricula.horas_reforzamiento else 16
            num_clases = horas // horas_por_dia
        else:
            num_clases = 16 // horas_por_dia

        fechas = []
        from datetime import date
        actual = date.fromisoformat(data['fecha_inicio']) if isinstance(data['fecha_inicio'], str) else data['fecha_inicio']
        while len(fechas) < num_clases:
            if es_extraordinario:
                if actual.weekday() >= 5:        # solo sábado y domingo
                    fechas.append(actual)
            else:
                if actual.weekday() < 5:         # lunes a viernes
                    fechas.append(actual)
            actual += timedelta(days=1)

        creadas = []
        try:
            with transaction.atomic():
                for i, f in enumerate(fechas, start=1):
                    cita = Calendario(
                        instructor_id=data['instructor_id'],
                        matricula_id=data['matricula_id'],
                        fecha=f,
                        hora_inicio=hora_inicio,
                        hora_fin=hora_fin,
                        numero_clase=i,
                    )
                    cita.save()
                    creadas.append(cita)
        except DjangoValidationError as e:
            return Response(
                {"error": e.messages if hasattr(e, 'messages') else str(e)},
                status=400,
            )

        return Response(
            {
                "message": f"Bloque de {num_clases} clases creado correctamente.",
                "fecha_inicio": fechas[0],
                "fecha_fin": fechas[-1],
                "clases_creadas": len(creadas),
                "citas": CalendarioSerializer(creadas, many=True).data,
            },
            status=201,
        )

    @action(detail=False, methods=['post'], url_path='crear-examen')
    def crear_examen(self, request):
        instructor_id = request.data.get('instructor_id')
        matricula_id = request.data.get('matricula_id')
        fecha = request.data.get('fecha')
        hora_inicio = request.data.get('hora_inicio', '08:00')
        hora_fin = request.data.get('hora_fin', '10:00')

        try:
            matricula = Matricula.objects.get(pk=matricula_id)
            instructor = Instructor.objects.get(pk=instructor_id)

            # Si ya existe un examen, lo reemplazamos
            Calendario.objects.filter(
                matricula_id=matricula_id,
                numero_clase=9,
            ).delete()

            examen = Calendario.objects.create(
                instructor=instructor,
                matricula=matricula,
                fecha=fecha,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
                numero_clase=9,
            )

            return Response({
                "message": "Examen programado correctamente",
                "examen": CalendarioSerializer(examen).data,
            }, status=201)

        except Matricula.DoesNotExist:
            return Response({"error": "Matrícula no encontrada"}, status=404)
        except Instructor.DoesNotExist:
            return Response({"error": "Instructor no encontrado"}, status=404)

@api_view(['POST','OPTIONS'])
@permission_classes([IsAuthenticated])
def justificar_clase(request):
    calendario_id = request.data.get('calendario_id')
    motivo = request.data.get('motivo', '')

    try:
        clase = Calendario.objects.get(id=calendario_id)
    except Calendario.DoesNotExist:
        return Response({'error': 'Clase no encontrada'}, status=404)

    matricula = clase.matricula
    tipo = matricula.tipo_curso

    dias_permitidos = {5, 6} if tipo == 'Reforzamiento' else {0, 1, 2, 3, 4}

    clase.justificada = True
    clase.motivo_justificacion = motivo
    clase.save()

    clases = list(
        Calendario.objects.filter(
            matricula=matricula,
            fecha__gte=clase.fecha
        ).order_by('fecha', 'numero_clase')
    )

    fecha_nueva = clase.fecha + timedelta(days=1)

    for c in clases:
        while fecha_nueva.weekday() not in dias_permitidos:
            fecha_nueva += timedelta(days=1)
        c.fecha = fecha_nueva
        c.save()
        fecha_nueva += timedelta(days=1)

    return Response({'mensaje': 'Clase justificada y reprogramada correctamente'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_asistencia(request):
    from datetime import date
    matriculas = Matricula.objects.all()  # sin select_related
    resultado = []

    if matricula.tipo_curso == 'Reforzamiento':
        try:
                recibo = matricula.recibos.order_by('-fecha_pago').first()
                horas = int(recibo.horas_reforzamiento) if recibo and recibo.horas_reforzamiento else 16
        except Exception:
            horas = 16
        max_clases = horas // 2
    else:
        max_clases = 8

    clases = Calendario.objects.filter(
        matricula=matricula,
        numero_clase__lte=max_clases
    ).order_by('numero_clase')

    asistencias = {}
    for clase in clases:
        asistencias[str(clase.numero_clase)] = {
                'id': clase.id,
                'fecha': clase.fecha.strftime('%Y-%m-%d') if clase.fecha else None,
                'asistio': clase.asistio,
                'justificada': clase.justificada,
                'motivo_justificacion': clase.motivo_justificacion,
        }

       
        clases_marcadas = clases.filter(asistio__isnull=False, justificada=False)
        presentes = clases_marcadas.filter(asistio=True).count()
        total_marcadas = clases_marcadas.count()
        porcentaje = round((presentes / total_marcadas) * 100) if total_marcadas > 0 else 0

        resultado.append({
            'matricula_id': matricula.id,
            'nombre': getattr(matricula, 'nombre', '') or '',
            'apellido': getattr(matricula, 'apellido', '') or '',
            'cedula': getattr(matricula, 'cedula', 'N/A'),
            'tipo_curso': getattr(matricula, 'tipo_curso', ''),
            'total_clases': max_clases,
            'asistencias': asistencias,
            'porcentaje': porcentaje,
        })

    return Response(resultado)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_asistencia(request):
    calendario_id = request.data.get('calendario_id')
    asistio = request.data.get('asistio')

    try:
        clase = Calendario.objects.get(id=calendario_id)
        clase.asistio = asistio
        clase.save()
        return Response({'mensaje': 'Asistencia registrada'})
    except Calendario.DoesNotExist:
        return Response({'error': 'Clase no encontrada'}, status=404)