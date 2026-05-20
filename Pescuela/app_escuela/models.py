from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre


class ValorCurso(models.Model):
    TIPO_CURSO_CHOICES = [
        ('Principiante', 'Principiante'),
        ('Intermedio', 'Intermedio'),
        ('Avanzado', 'Avanzado'),
    ]
    
    tipo_curso = models.CharField(
        max_length=50,
        choices=TIPO_CURSO_CHOICES
    )
    precio_hora = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    cantidad_horas = models.PositiveIntegerField(
        default=15
    )
    precio_total = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Valor del Curso"
        verbose_name_plural = "Valores de Cursos"
        ordering = ['-fecha_modificacion']

    def __str__(self):
        return f"{self.tipo_curso} - C${self.precio_total}"

class Usuario(AbstractUser):
    rol = models.ForeignKey(
        Rol,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuarios'
    )

    estudiante = models.ForeignKey(
        'Estudiante',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuarios'
    )

    instructor = models.ForeignKey(
        'Instructor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuarios'
    )

    @property
    def rol_nombre(self):
        return self.rol.nombre.lower() if self.rol else ""

    def __str__(self):
        return f"{self.username} - {self.rol_nombre}"


class CategoriaVehiculo(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre


class Instructor(models.Model):
    nombre = models.CharField(max_length=30)
    apellido = models.CharField(max_length=30)
    foto = models.ImageField(upload_to='instructores/', blank=True, null=True)
    numero_telefono = models.CharField(max_length=20, blank=True, null=True)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    categoria_instructor = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    experiencia = models.TextField(blank=True, null=True)
    edad = models.PositiveIntegerField(blank=True, null=True)
    cedula = cedula = models.CharField(max_length=20, unique=True, blank=True, null=True)
    nacionalidad = models.CharField(max_length=100, blank=True, null=True)
    nivel_escolar = models.CharField(max_length=100, blank=True, null=True)
    antecedentes_penales = models.CharField(
        max_length=20,
        choices=[
            ('Si', 'Sí'),
            ('No', 'No'),
        ],
        default='No'
    )
    centro_trabajo = models.CharField(max_length=150, blank=True, null=True)
    cargo = models.CharField(max_length=100, blank=True, null=True)
    curso_aprobado_instructor = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )
    fecha_ingreso = models.DateField(blank=True, null=True)
    fecha_salida = models.DateField(blank=True, null=True)
    motivo_salida = models.TextField(blank=True, null=True)
    infracciones_resoluciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombre} , {self.apellido}"


class Estudiante(models.Model):
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

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    edad = models.PositiveIntegerField()
    sexo = models.CharField(max_length=10, choices=SEXO_CHOICES)
    nacionalidad = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20, unique=True)
    fecha_nacimiento = models.DateField()
    cedula = models.CharField(max_length=20, unique=True)
    direccion = models.CharField(max_length=200)
    correo_electronico = models.EmailField(max_length=254, unique=True)
    telefono_movil = models.CharField(max_length=100)
    nivel_educativo = models.CharField(max_length=50, choices=NIVEL_EDUCATIVO_CHOICES)
    nombre_emergencia = models.CharField(max_length=100)
    telefono_emergencia = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.cedula}"

class Matricula(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('matriculado', 'Matriculado'),
    ]
    
    MODALIDADES = [
        ('Regular', 'Regular'),
        ('Extraordinario', 'Extraordinario'),
    ]
    
    HORARIOS = [
        ('06AM', '06:00 AM'),
        ('08AM', '08:00 AM'),
        ('10AM', '10:00 AM'),
        ('12PM', '12:00 PM'),
        ('04PM', '04:00 PM'),
    ]
    
    TIPOS_CURSO = [
        ('Principiante', 'Principiante'),
        ('Intermedio', 'Intermedio'),
        ('Avanzado', 'Avanzado'),
    ]
    
    APARICIONES = [
        ('Redes_Sociales', 'Redes Sociales'),
        ('Referido', 'Referido'),
        ('Sitio_Web', 'Sitio Web'),
        ('otro', 'otro'),
    ]

    plan_de_estudio = models.ForeignKey(
    'PlanEstudio',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='matriculas'
        )
    
    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name='matriculas')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    categoria = models.ForeignKey(CategoriaVehiculo, on_delete=models.SET_NULL, null=True, blank=True, related_name='matriculas')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    modalidad = models.CharField(max_length=50, choices=MODALIDADES)
    horario = models.CharField(max_length=10, choices=HORARIOS)
    tipo_curso = models.CharField(max_length=50, choices=TIPOS_CURSO)
    horas_reforzamiento = models.PositiveSmallIntegerField(null=True,blank=True)
    aparicion = models.CharField(max_length=50, choices=APARICIONES)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Matrícula #{self.id} - {self.estudiante.nombre} {self.estudiante.apellido}"


class Recibo(models.Model):
    ESTADO_CHOICES = [
        ('pagado', 'Pagado'),
        ('anticipo', 'Anticipo'),
        ('anulado', 'Anulado'),
    ]

    TIPO_PAGO_CHOICES = [
        ('completo', 'Completo'),
        ('anticipo', 'Anticipo'),
        ('beneficio', 'Beneficio'),
    ]


    matricula = models.ForeignKey(
    Matricula,
    on_delete=models.CASCADE,
    related_name='recibos'
    )

    valor_curso = models.ForeignKey(
        ValorCurso,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recibos'
    )

    numero_recibo = models.CharField(max_length=50, unique=True)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateField(default=timezone.now)
    tipo_pago = models.CharField(max_length=20, choices=TIPO_PAGO_CHOICES)
    cantidad = models.PositiveSmallIntegerField(default=15)
    monto_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('433.33'))
    concepto = models.CharField(max_length=200, default='Pago de curso')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='anticipo')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-fecha_pago']

    def __str__(self):
        estudiante = self.matricula.estudiante
        return f"Recibo #{self.numero_recibo} - {estudiante.nombre} {estudiante.apellido}"


class Calendario(models.Model):

    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('completada', 'Completada'),
        ('inasistencia', 'Inasistencia'),
        ('reprogramada', 'Reprogramada'),
    ]

    matricula = models.ForeignKey(
        Matricula,
        on_delete=models.CASCADE,
        related_name='clases'
    )

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name='agenda'
    )

    modulo = models.ForeignKey(
        'PlanEstudio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clases'
    )

    fecha = models.DateField()

    hora_inicio = models.TimeField()

    hora_fin = models.TimeField()

    numero_clase = models.PositiveSmallIntegerField()

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='pendiente'
    )

    es_examen = models.BooleanField(default=False)

    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['fecha', 'hora_inicio']

    def __str__(self):
        estudiante = self.matricula.estudiante
        return f"{estudiante.nombre} {estudiante.apellido} - Clase {self.numero_clase}"


class Asistencia(models.Model):
    ESTADO_CHOICES = [
        ('asistio', 'Asistió'),
        ('falto', 'Faltó'),
        ('justificado', 'Justificado'),
    ]

    As_estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE)
    As_calendario = models.OneToOneField(Calendario, on_delete=models.CASCADE)

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='falto'
    )

    observacion = models.TextField(
        blank=True,
        null=True
    )

    justificado_por_admin = models.BooleanField(default=False)
    km_inicial = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    null=True,
    blank=True
    )

    km_final = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    km_recorridos = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)


    def save(self, *args, **kwargs):
        if self.km_inicial is not None and self.km_final is not None:
            self.km_recorridos = self.km_final - self.km_inicial
        else:
            self.km_recorridos = 0

        super().save(*args, **kwargs)
    
    def __str__(self):
        
        return f"{self.As_estudiante}  {self.As_calendario}"


class Notas(models.Model):

    TIPO_NOTA_CHOICES = [
        ('practico', 'Examen práctico'),
        ('teorico', 'Examen teórico'),
    ]
       
    matricula = models.ForeignKey(
        Matricula,
        on_delete=models.CASCADE,
        related_name='notas'
    )

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name='notas_registradas'
    )

    plan_de_estudio = models.ForeignKey(
        'PlanEstudio',
        on_delete=models.CASCADE,
        related_name='notas'
    )
    

    tipo_nota = models.CharField(
        max_length=20,
        choices=TIPO_NOTA_CHOICES,
        default='practico'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    nota = models.CharField(max_length=10)
    comentario = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"Notas de {self.matricula.estudiante} - {self.nota}"


class PlanEstudio(models.Model):

    TIPO_CURSO_CHOICES = [
        ('Principiante', 'Principiante'),
        ('Intermedio', 'Intermedio'),
        ('Avanzado', 'Avanzado'),
    ]

    nombre = models.CharField(max_length=100)

    tipo_curso = models.CharField(
        max_length=50,
        choices=TIPO_CURSO_CHOICES
    )

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Plan de Estudio"
        verbose_name_plural = "Planes de Estudios"
        ordering = ['tipo_curso', 'nombre']

    def __str__(self):
        return f"{self.nombre} - {self.tipo_curso}"


class TemaPlanEstudio(models.Model):

    plan_estudio = models.ForeignKey(
        'PlanEstudio',
        on_delete=models.CASCADE,
        related_name='temas'
    )

    titulo = models.CharField(max_length=150)

    orden = models.PositiveSmallIntegerField(default=1)

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tema"
        verbose_name_plural = "Temas"
        ordering = ['orden', 'id']

    def __str__(self):
        return f"{self.plan_estudio.tipo_curso} - {self.titulo}"


class SubtemaPlanEstudio(models.Model):

    tema = models.ForeignKey(
        'TemaPlanEstudio',
        on_delete=models.CASCADE,
        related_name='subtemas'
    )

    titulo = models.CharField(max_length=150)

    orden = models.PositiveSmallIntegerField(default=1)

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Subtema"
        verbose_name_plural = "Subtemas"
        ordering = ['orden', 'id']

    def __str__(self):
        return f"{self.tema.titulo} - {self.titulo}"
    



   # models.py


class ProgresoTema(models.Model):

    matricula = models.ForeignKey(
        'Matricula',
        on_delete=models.CASCADE,
        related_name='progresos_temas'
    )

    tema = models.ForeignKey(
        'TemaPlanEstudio',
        on_delete=models.CASCADE,
        related_name='progresos_estudiantes'
    )

    orden_general = models.IntegerField(default=0)

    estudiante_completado = models.BooleanField(default=False)

    instructor_completado = models.BooleanField(default=False)

    desbloqueado = models.BooleanField(default=False)

    completado = models.BooleanField(default=False)

    fecha_estudiante = models.DateTimeField(null=True, blank=True)

    fecha_instructor = models.DateTimeField(null=True, blank=True)

    fecha_completado = models.DateTimeField(null=True, blank=True)

    fecha_admin_edit = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['matricula', 'tema']
        ordering = ['orden_general', 'tema__orden', 'id']  # ← CAMBIAR ES

    def __str__(self):
        return f"{self.matricula.estudiante.nombre} - {self.tema.titulo}"

    @property
    def ambos_checks_completados(self):
        return (
            self.estudiante_completado and
            self.instructor_completado
        )


class Notificacion(models.Model):
    """Notificaciones para el administrador"""
    
    TIPOS_NOTIFICACION = (
    ('falta_estudiante', 'El estudiante no ha marcado su tema'),
    ('falta_instructor', 'El instructor no ha marcado la clase'),
    ('tema_bloqueado', 'Tema bloqueado'),
    ('tema_desbloqueado', 'Tema desbloqueado'),
    ('intervencion_admin', 'El admin realizó una intervención'),
    ('plan_completado', 'El estudiante completó todo el plan'),
)
    
    estudiante = models.ForeignKey('Usuario', on_delete=models.CASCADE, related_name='notificaciones')
    tema = models.ForeignKey('TemaPlanEstudio', on_delete=models.CASCADE, null=True, blank=True)

    tipo = models.CharField(max_length=30, choices=TIPOS_NOTIFICACION)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-fecha_creacion']
        constraints = [
            models.UniqueConstraint(
                fields=['estudiante','tema','tipo'],
                name='notificacion_unica_por_tema_tipo'
            )
        ]


    def __str__(self):
        return f"{self.tipo} - {self.estudiante.username}"


class HistorialPlanEstudio(models.Model):
    """Historial de cambios en el progreso"""
    
    progreso_tema = models.ForeignKey(ProgresoTema, on_delete=models.CASCADE, related_name='historial')
    usuario = models.ForeignKey('Usuario', on_delete=models.CASCADE)
    accion = models.CharField(max_length=50)
    valor_anterior_estudiante = models.BooleanField(null=True)
    valor_anterior_instructor = models.BooleanField(null=True)
    valor_nuevo_estudiante = models.BooleanField(null=True)
    valor_nuevo_instructor = models.BooleanField(null=True)
    fecha = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.fecha} - {self.usuario.username} - {self.accion}"





class PreguntaExamenTeorico(models.Model):
    texto = models.TextField()
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.fecha_creacion} - {self.texto[:50]}"


class OpcionPreguntaExamenTeorico(models.Model):

    pregunta = models.ForeignKey(
        PreguntaExamenTeorico,
        on_delete=models.CASCADE,
        related_name='opciones'
    )

    texto = models.TextField()

    es_correcta = models.BooleanField(default=False)

    def __str__(self):
        return self.texto[:50]


class ExamenTeorico(models.Model):

    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('habilitado', 'Habilitado'),
        ('realizado', 'Realizado'),
    ]

    matricula = models.OneToOneField(
        Matricula,
        on_delete=models.CASCADE,
        related_name='examen_teorico'
    )

    habilitado_por = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='examenes_teoricos_habilitados'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='pendiente'
    )

    nota = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    fecha_habilitado = models.DateTimeField(null=True, blank=True)

    fecha_realizado = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        estudiante = self.matricula.estudiante
        return f"Examen teórico - {estudiante.nombre} {estudiante.apellido}"


class RespuestaExamenTeorico(models.Model):

    examen = models.ForeignKey(
        ExamenTeorico,
        on_delete=models.CASCADE,
        related_name='respuestas'
    )

    pregunta = models.ForeignKey(
        PreguntaExamenTeorico,
        on_delete=models.CASCADE
    )

    opcion_seleccionada = models.ForeignKey(
        OpcionPreguntaExamenTeorico,
        on_delete=models.CASCADE
    )

    correcta = models.BooleanField(default=False)

    def __str__(self):
        return f"Respuesta examen #{self.examen.id}"