# app_escuela/models.py
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from datetime import time # Asegúrate de importar esto arriba

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
    
    tipo_curso = models.CharField(max_length=50, choices=TIPO_CURSO_CHOICES)
    categoria = models.CharField(max_length=50, choices=CATEGORIA_CHOICES)
    apariconia = models.CharField(max_length=100, choices=APARICIONIA_CHOICES)


    def obtener_rango_horario(self):
        """
        Esta función hace el trabajo sucio: convierte tu texto 
        en objetos de tiempo (datetime.time) para poder compararlos.
        """
        mapeo = {
            '6AM A 8AM': (time(6, 0), time(8, 0)),
            '8AM A 10AM': (time(8, 0), time(10, 0)),
            '10AM A 12PM': (time(10, 0), time(12, 0)),
            '12PM A 2PM': (time(12, 0), time(14, 0)),
            '4PM A 6PM': (time(16, 0), time(18, 0)),
        }
        return mapeo.get(self.horario)
    
    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.cedula}"
    
   


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


from django.core.exceptions import ValidationError # Asegúrate de importar esto arriba

class Calendario(models.Model):
    matricula = models.ForeignKey('Matricula', on_delete=models.CASCADE, related_name='citas')
    instructor = models.ForeignKey('Instructor', on_delete=models.CASCADE, related_name='agenda')
    fecha = models.DateField()
    hora_inicio = models.TimeField()

    def clean(self):
        # 1. Llamamos a la función de la matrícula relacionada
        rango = self.matricula.obtener_rango_horario()
        
        # 2. Verificamos que el rango exista
        if not rango:
            raise ValidationError("La matrícula no tiene un horario definido correctamente.")
        
        inicio_permitido, fin_permitido = rango
        
        # 3. Validamos: ¿Está la hora_inicio de la cita dentro del rango permitido?
        if not (inicio_permitido <= self.hora_inicio < fin_permitido):
            raise ValidationError(
                f"Error: La hora {self.hora_inicio} no coincide con el horario "
                f"de la matrícula ({self.matricula.horario}). "
                f"El horario debe estar entre {inicio_permitido.strftime('%H:%M')} y {fin_permitido.strftime('%H:%M')}."
            )
        
        super().clean() # Llamamos al clean original de Django

    
    
    # Para cumplir con tu requerimiento de "no permitir duplicados en la misma fecha y hora"
    class Meta:
        unique_together = ('instructor', 'fecha', 'hora_inicio')

    def __str__(self):
        return f"Cita: {self.matricula.nombre} con {self.instructor.usuario.username} el {self.fecha}"

class Notas(models.Model) :
    Matricula = models.OneToOneField('Matricula', on_delete=models.CASCADE, related_name='notas')
    user = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    examen_practico = models.IntegerField(null=True, blank=True)
    examen_teorico = models.IntegerField(null=True, blank=True)
def __str__ (self):
    return f"notas de {self.Matricula.nombre}"
