# app_escuela/api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter # type: ignore
from .views import MatriculaViewSet, ReciboViewSet, UserViewSet, login, saldo,exportar_egresados_excel




router = DefaultRouter()
router.register(r'matricula', MatriculaViewSet)
router.register(r'recibo', ReciboViewSet)
router.register(r'usuarios', UserViewSet)

urlpatterns = [
    path('login/', login, name='login'),
    path('saldo/', saldo, name='saldo'),
    path('api/reporte-excel/', exportar_egresados_excel, name='exporte_egresado_excel'),
    path('', include(router.urls)),
    
]

