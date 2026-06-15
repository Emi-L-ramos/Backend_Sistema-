# app_escuela/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DashboardIngresosMensualesView,
    RolViewSet,
    UserViewSet,
    CargoInstitucionalViewSet,
    EstudianteViewSet,
    InstructorViewSet,
    PagoInstructorViewSet,
    CategoriaVehiculoViewSet,
    PlanEstudioViewSet,
    ValorCursoViewSet,
    MatriculaViewSet,
    ReciboViewSet,
    CalendarioViewSet,
    AsistenciaViewSet,
    NotasViewSet,
    login,
    saldo,
    DashboardGananciasView,
    DashboardResumenView,
    DashboardPlanViewSet,
    PreguntaExamenTeoricoViewSet,
    ExamenTeoricoViewSet,
    PerfilView,
    exportar_reporte_instructores_policial,
    reporte_induccion_instructores,
    reporte_kilometros_instructor,
    certificados_egresados,
    certificados_egresados_word,
)
from .views import ( ProgresoTemaViewSet, NotificacionViewSet
)


router = DefaultRouter()

router.register(r'roles', RolViewSet)
router.register(r'usuarios', UserViewSet, basename='usuarios')
router.register(r'estudiantes', EstudianteViewSet)
router.register(r'instructores', InstructorViewSet)
router.register(r'categorias', CategoriaVehiculoViewSet)
router.register(r'plan-estudio', PlanEstudioViewSet)
router.register(r'valores-curso', ValorCursoViewSet)
router.register(r'matricula', MatriculaViewSet)
router.register(r'recibo', ReciboViewSet)
router.register(r'calendario', CalendarioViewSet)
router.register(r'asistencia', AsistenciaViewSet)
router.register(r'notas', NotasViewSet, basename='notas')
router.register(r'progreso-tema', ProgresoTemaViewSet, basename='progreso-tema')
router.register(r'notificaciones', NotificacionViewSet)
router.register(r'dashboard-plan', DashboardPlanViewSet, basename='dashboard-plan')
router.register(r'preguntas-examen-teorico', PreguntaExamenTeoricoViewSet)
router.register(r'examen-teorico', ExamenTeoricoViewSet)
router.register(r'pagos-instructor', PagoInstructorViewSet, basename='pagos-instructor')
router.register(r'cargos-institucionales', CargoInstitucionalViewSet, basename='cargos-institucionales')


# app_escuela/api/urls.py

urlpatterns = [
    path('', include(router.urls)),
    path('login/', login, name='login'),
    path('saldo/', saldo, name='saldo'),
    path('perfiles/', PerfilView.as_view(), name='perfiles'),
    path('dashboard/ganancias/', DashboardGananciasView.as_view(), name='dashboard-ganancias'),
    path('dashboard/resumen/', DashboardResumenView.as_view(), name='dashboard-resumen'),  
    path('dashboard/ingresos-mensuales/', DashboardIngresosMensualesView.as_view(), name='dashboard-ingresos-mensuales'),
    path(
        'reporte-instructores-policial/',
        exportar_reporte_instructores_policial,
        name='reporte_instructores_policial'
    ),
    path(
        'reporte-induccion-instructores/',
        reporte_induccion_instructores,
        name='reporte_induccion_instructores'
    ),
    path(
        'reporte-kilometros-instructor/',
        reporte_kilometros_instructor,
        name='reporte_kilometros_instructor'
    ),

    path(
        'certificados-egresados/',
        certificados_egresados,
        name='certificados_egresados'
    ),
    path(
        'certificados-egresados-word/',
        certificados_egresados_word,
        name='certificados_egresados_word'
    ),
]