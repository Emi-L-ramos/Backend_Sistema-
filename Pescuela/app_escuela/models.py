# app_escuela/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    ROLES = (
        ('admin', 'Administrador'),
        ('instructor', 'Instructor'),
        ('secretaria', 'Secretaria'),
        ('cajero', 'Cajero'),
        ('consulta', 'Solo Consulta'),
    )
    rol = models.CharField(max_length=20, choices=ROLES, default='admin')
    
    def tiene_permiso(self, permiso):
        permisos = {
            'admin': ['*'],
            'secretaria': ['ver_matriculas', 'crear_matriculas', 'editar_matriculas', 
                          'ver_recibos', 'crear_recibos', 'exportar'],
            'cajero': ['ver_matriculas', 'ver_recibos', 'crear_recibos', 'editar_recibos', 'exportar'],
            'consulta': ['ver_matriculas', 'ver_recibos'],
            'instructor': ['ver_matriculas', 'ver_recibos']
        }
        
        if permiso in permisos.get(self.rol, []) or '*' in permisos.get(self.rol, []):
            return True
        return False

    def __str__(self):
        return f"{self.username} - {self.get_rol_display()}"


class Instructor(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, null=True, blank=True)
    especialidad = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.usuario.username if self.usuario else "Instructor sin usuario"


class Matricula(models.Model):
    TIPO_PAGO_CHOICES = [
        ('Pago_completo', 'Pago completo'),
        ('Anticipo', 'Anticipo'),
        ('Beneficio', 'Beneficio'),
    ]

    TIPO_CURSO_CHOICES = [
        ('Curso_regular', 'Curso Regular'),  
        ('Reforzamiento', 'Reforzamiento'),
    ]

    CATEGORIA_CHOICES = [
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
    ]

    APARICIONIA_CHOICES = [
        ('Redes_Sociales', 'Redes Sociales'),
        ('Referido', 'Referido'),
        ('Sitio_Web', 'Sitio Web'),
        ('otro', 'Otro'),
    ]

    SEXO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Femenino'),
    ]
    

    NIVEL_EDUCATIVO_CHOICES = [
        ('Primaria', 'Primaria'),
        ('Secundaria', 'Secundaria'),
        ('Universidad', 'Universidad'),
        ('Profesional', 'Profesional'),
    ]

    HORARIO_CHOICES = [
        ('6AM A 8AM', '6AM A 8AM'),      # ✅ Corregido
        ('8AM A 10AM', '8AM A 10AM'),    # ✅ Corregido
        ('10AM A 12PM', '10AM A 12PM'),  # ✅ Corregido
        ('12PM A 2PM', '12PM A 2PM'),    # ✅ Corregido (cambié 02PM a 2PM)
        ('4PM A 6PM', '4PM A 6PM'),      # ✅ Corregido (cambié 04PM a 4PM)
        
    ]

    MODALIDAD_CHOICES = [
        ('Regular', 'Regular'),
        ('Extraordinario', 'Extraordinario'),
    ]

    f_matricula = models.DateField(auto_now_add=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    edad=models.CharField(max_length=100)
    sexo = models.CharField(max_length=10, choices=SEXO_CHOICES)
    nacionalidad=models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    cedula = models.CharField(max_length=20, unique=True)
    direccion = models.CharField(max_length=200)
    correo_electronico = models.EmailField(unique=True)
    
    telefono_movil = models.CharField(max_length=100)
    nivel_educativo = models.CharField(max_length=50, choices=NIVEL_EDUCATIVO_CHOICES)
    profesion_u_oficio = models.CharField(max_length=100)
    en_caso_de_emrgencia= models.CharField(max_length=100)
    telefono_emergencia = models.CharField(max_length=100)
    modalidad = models.CharField(max_length=50, choices=MODALIDAD_CHOICES)
    horario = models.CharField(max_length=50, choices=HORARIO_CHOICES)
    tipo_pago = models.CharField(max_length=50, choices=TIPO_PAGO_CHOICES)
    tipo_curso = models.CharField(max_length=50, choices=TIPO_CURSO_CHOICES)
    categoria = models.CharField(max_length=50, choices=CATEGORIA_CHOICES)
    apariconia = models.CharField(max_length=100, choices=APARICIONIA_CHOICES)
    
    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.cedula}"
    
    @property
    def saldo_pendiente(self):
        return self.monto_total - self.monto_pagado


class Recibo(models.Model):
    ESTADO_CHOICES = [
        ('pagado', 'Pagado'),
        ('anticipo', 'Anticipo')
    ]
    
    METODO_PAGO_CHOICES = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia Bancaria'),
        ('tarjeta', 'Tarjeta de Crédito/Débito'),
        ('cheque', 'Cheque'),

    ]

    matricula = models.ForeignKey(Matricula, on_delete=models.CASCADE, related_name='recibos')
    numero_recibo = models.CharField(max_length=50, unique=True)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Recibo #{self.numero_recibo} - {self.matricula.nombre} - C${self.monto_pagado}"

class Calendario(models.Model) :
    Matricula = models.OneToOneField('Matricula', on_delete=models.CASCADE, related_name='calendario')
    user = models.ForeignKey('Usuario', on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

def __str__ (self):
    return f"calendario de {self.Matricula.nombre}"

class Notas(models.Model) :
    Matricula = models.OneToOneField('Matricula', on_delete=models.CASCADE, related_name='notas')
    user = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    examen_practico = models.IntegerField(null=True, blank=True)
    examen_teorico = models.IntegerField(null=True, blank=True)
def __str__ (self):
    return f"notas de {self.Matricula.nombre}"
