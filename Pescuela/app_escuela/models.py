from django.db import models


class Matricula(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    sexo = models.CharField(max_length=10)
    cedula = models.CharField(max_length=20, unique=True)
    direccion = models.CharField(max_length=200)
    correo_electronico = models.EmailField(unique=True)
    nivel_educativo = models.CharField(max_length=50)
    oficio = models.CharField(max_length=100)
    numero_telefono = models.CharField(max_length=20)
    fecha_nacimiento = models.DateField()
    grado = models.CharField(max_length=50)
    nombre_padre = models.CharField(max_length=100)
    n_emergencia = models.CharField(max_length=100)
    apariconia = models.CharField(max_length=100)
    f_matricula = models.DateField(auto_now_add=True)
    categoria = models.CharField(max_length=50)
    tipo_pago = models.CharField(max_length=50)
    tipo_curso = models.CharField(max_length=50)
    descripcion = models.TextField()
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    

    def __str__(self):
        return f"{self.nombre} {self.apellido}"