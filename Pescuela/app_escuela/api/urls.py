from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MatriculaViewSet, ReciboViewSet, UserViewSet, dashboard_ganancias, dashboard_resumen,
    login, saldo, exportar_egresados_excel,
    CalendarioViewSet, InstructorViewSet,
    listar_asistencia, marcar_asistencia, justificar_clase
)

router = DefaultRouter()
router.register(r'matricula', MatriculaViewSet)
router.register(r'recibo', ReciboViewSet)
router.register(r'usuarios', UserViewSet)
router.register(r'calendario', CalendarioViewSet)
router.register(r'instructores', InstructorViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('login/', login, name='login'),
    path('saldo/', saldo, name='saldo'),
    path('reporte-excel/', exportar_egresados_excel, name='exporte_egresado_excel'),
    path('asistencia/', listar_asistencia),
    path('asistencia/marcar/', marcar_asistencia),
    path('justificar-clase/', justificar_clase),
    path('dashboard/ganancias/', dashboard_ganancias),
    path('dashboard/resumen/', dashboard_resumen),
]