
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import MatriculaViewSet, Matricula
from rest_framework.authtoken.views import obtain_auth_token

router = DefaultRouter()
router.register(r'matricula', MatriculaViewSet)

urlpatterns = [
    path('login/', obtain_auth_token),
    path('matricula/', include(router.urls)),
    
]