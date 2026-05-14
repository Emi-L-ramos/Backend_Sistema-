# app_escuela/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    DashboardIngresosMensualesView,
    RolViewSet,
    UserViewSet,
    EstudianteViewSet,
    InstructorViewSet,
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
    
    DashboardPlanViewSet
)
from .views import ( ProgresoTemaViewSet, NotificacionViewSet
)


router = DefaultRouter()

router.register(r'roles', RolViewSet)
router.register(r'usuarios', UserViewSet)
router.register(r'estudiantes', EstudianteViewSet)
router.register(r'instructores', InstructorViewSet)
router.register(r'categorias', CategoriaVehiculoViewSet)
router.register(r'plan-estudio', PlanEstudioViewSet)
router.register(r'valores-curso', ValorCursoViewSet)
router.register(r'matricula', MatriculaViewSet)
router.register(r'recibo', ReciboViewSet)
router.register(r'calendario', CalendarioViewSet)
router.register(r'asistencia', AsistenciaViewSet)
router.register(r'notas', NotasViewSet)
router.register(r'progreso-tema', ProgresoTemaViewSet, basename='progreso-tema')
router.register(r'notificaciones', NotificacionViewSet)
router.register(r'dashboard-plan', DashboardPlanViewSet, basename='dashboard-plan')

# app_escuela/api/urls.py

urlpatterns = [
    path('', include(router.urls)),
    path('login/', login, name='login'),
    path('saldo/', saldo, name='saldo'),
    path('dashboard/ganancias/', DashboardGananciasView.as_view(), name='dashboard-ganancias'),
    path('dashboard/resumen/', DashboardResumenView.as_view(), name='dashboard-resumen'),  
    path('dashboard/ingresos-mensuales/', DashboardIngresosMensualesView.as_view(), name='dashboard-ingresos-mensuales'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)