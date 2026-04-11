from rest_framework.viewsets import ModelViewSet
from ..models import Matricula
from .serializers import MatriculaSerializer    
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

class MatriculaViewSet(ModelViewSet):
    queryset = Matricula.objects.all()  
    serializer_class = MatriculaSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pacientes(request):
    return Response({
        "mensaje": "Acceso autorizado",
        "usuario": request.user.username
    })

