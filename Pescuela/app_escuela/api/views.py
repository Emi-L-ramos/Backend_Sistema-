# app_escuela/api/views.py
import openpyxl
from django.db.models import Sum
from django.http import HttpResponse
from rest_framework.viewsets import ModelViewSet 
from rest_framework.decorators import api_view, permission_classes 
from rest_framework.permissions import IsAuthenticated, AllowAny 
from rest_framework.response import Response 
from rest_framework.authtoken.models import Token 
from django.contrib.auth import authenticate
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError

from ..models import Matricula, Recibo, Usuario, Calendario, Notas
from .serializers import (
    MatriculaSerializer, 
    ReciboSerializer, 
    UserSerializer, 
    ReporteExcelSerializer
)

class MatriculaViewSet(ModelViewSet):
    queryset = Matricula.objects.all()  
    serializer_class = MatriculaSerializer
    permission_classes = [IsAuthenticated]

class ReciboViewSet(ModelViewSet):
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except DjangoValidationError as e:
            return Response(
                {"error": e.messages[0] if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except DjangoValidationError as e:
            return Response(
                {"error": e.messages[0] if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class UserViewSet(ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

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
            'last_name': user.last_name
        })
    return Response({'error': 'Credenciales inválidas'}, status=401)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exportar_egresados_excel(request):
    """Genera reporte Excel basado en la fecha de finalización del calendario"""
    mes = request.query_params.get('mes')
    anio = request.query_params.get('anio')

    if not mes or not anio:
        return Response({"error": "Se requieren los parámetros 'mes' y 'anio'"}, status=400)

    egresados = Matricula.objects.filter(
        calendario__fecha_fin__month=mes,
        calendario__fecha_fin__year=anio
    ).select_related('calendario', 'notas')

    if not egresados.exists():
        return Response({"error": "No hay egresados para la fecha seleccionada"}, status=404)

    # Serializar datos
    serializer = ReporteExcelSerializer(egresados, many=True)
    data = serializer.data

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Egresados_{mes}_{anio}"

    headers = [
        'Nombre', 'Apellido', 'Nacionalidad', 'Cédula', 'Teléfono', 
        'Nivel Escolar', 'Tipo de Curso', 'Categoría', 
        'Fecha Inicio Matrícula', 'Fecha Finalización', 'Calificación Práctica', 'Calificación Teórica'
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
    response['Content-Disposition'] = f'attachment; filename="Reporte_Egresados_{mes}_{anio}.xlsx"'
    wb.save(response)
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def saldo(request):
    matricula_id = request.query_params.get('matricula')
    if not matricula_id:
        return Response({"error": "Se requiere el ID de la matrícula"}, status=400)

    try:
        matricula = Matricula.objects.get(id=matricula_id)
        recibos = matricula.recibos.all()

        tipo_matricula = str(matricula.tipo_curso).lower()

        if 'reforz' in tipo_matricula:
            tipo_curso = 'reforzamiento'
            horas = int(request.query_params.get('horas', 1))
            horas = max(1, min(horas, 15))
            monto_total = horas * 433.33
        else:
            tipo_curso = 'regular'
            horas = 15
            monto_total = 6500

        total_pagado = float(matricula.recibos.aggregate(total=Sum('monto_pagado'))['total'] or 0)
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
            "precio_hora_reforzamiento": 433.33
        })

    except Matricula.DoesNotExist:
        return Response({"error": "Matrícula no encontrada"}, status=404)