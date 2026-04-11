from rest_framework.serializers import ModelSerializer
from ..models import Matricula

class MatriculaSerializer(ModelSerializer):
    class Meta:
        model = Matricula
        fields = '__all__'