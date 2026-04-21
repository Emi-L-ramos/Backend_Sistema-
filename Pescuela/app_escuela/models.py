# app_escuela/models.py
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.db import models
from decimal import Decimal
from rest_framework.exceptions import ValidationError

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

    TIPO_PAGO_CHOICES = [
        ('completo', 'Completo'),
        ('anticipo', 'Anticipo'),
        ('beneficio', 'Beneficio'),
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

    tipo_pago = models.CharField(max_length=20, choices=TIPO_PAGO_CHOICES, default='anticipo')
    cantidad = models.PositiveSmallIntegerField(default=15)
    monto_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('433.33'))
    concepto = models.CharField(max_length=200, default='Pago de curso')
    monto_cordobas = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_dolares = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tasa_cambio = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('36.60'))
    tipo_curso = models.CharField(max_length=20, default='regular')
    horas_reforzamiento = models.PositiveSmallIntegerField(null=True, blank=True)

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)
    observaciones = models.TextField(blank=True, null=True)

    def _calcular_monto_total_curso(self):
        """Devuelve el monto total esperado del curso para esta matrícula."""
        tipo_matricula = str(self.matricula.tipo_curso).lower()
        if 'reforz' in tipo_matricula:
            horas = int(self.horas_reforzamiento or self.cantidad or 1)
            horas = max(1, min(horas, 15))
            return Decimal(horas) * Decimal('433.33')
        return Decimal('6500')

    def save(self, *args, **kwargs):
        from django.db.models import Sum

        tipo_matricula = str(self.matricula.tipo_curso).lower()
        self.tipo_curso = 'reforzamiento' if 'reforz' in tipo_matricula else 'regular'

        if self.tipo_curso == 'regular':
            self.cantidad = 15
            self.horas_reforzamiento = None
            self.monto_unitario = Decimal('433.33')
        else:
            if not self.horas_reforzamiento:
                self.horas_reforzamiento = self.cantidad or 1
            self.horas_reforzamiento = max(1, min(int(self.horas_reforzamiento), 15))
            self.cantidad = self.horas_reforzamiento
            self.monto_unitario = Decimal('433.33')

        if not self.monto_cordobas:
            self.monto_cordobas = self.monto_pagado
        if not self.monto_pagado:
            self.monto_pagado = self.monto_cordobas

        # === VALIDACIONES NUEVAS ===
        # Solo validamos en creación (no en updates)
        is_new = self._state.adding

        if is_new:
            recibos_previos = Recibo.objects.filter(matricula=self.matricula)
            cantidad_previos = recibos_previos.count()

            # Si ya hay un recibo "completo" o "beneficio" → bloquear
            if recibos_previos.filter(tipo_pago__in=['completo', 'beneficio']).exists():
                raise ValidationError(
                    "Esta matrícula ya tiene un recibo finalizado (Completo o Beneficio). No se pueden agregar más."
                )

            # BENEFICIO: monto libre, solo se permite UN recibo de beneficio y cierra la cuenta
            if self.tipo_pago == 'beneficio':
                if cantidad_previos >= 2:
                    raise ValidationError("Ya se registraron los 2 pagos máximos para esta matrícula.")
                self.estado = 'pagado'

            # ANTICIPO: máximo 2, el segundo debe cubrir el saldo exacto
            elif self.tipo_pago == 'anticipo':
                if cantidad_previos >= 2:
                    raise ValidationError(
                        "Ya se registraron los 2 anticipos permitidos. No se puede agregar otro recibo."
                    )

                monto_total = self._calcular_monto_total_curso()
                total_pagado_previo = recibos_previos.aggregate(t=Sum('monto_pagado'))['t'] or Decimal('0')
                saldo_pendiente = monto_total - total_pagado_previo

                if cantidad_previos == 1:
                    # Es el SEGUNDO anticipo → debe ser exactamente el saldo pendiente
                    if round(float(self.monto_pagado)) != round(float(saldo_pendiente)):
                        raise ValidationError(
                            f"El segundo pago debe cubrir exactamente el saldo pendiente: C${round(float(saldo_pendiente))}"
                        )
                    # Consolidar: en lugar de dejar 2 anticipos → eliminamos el primero
                    # y guardamos este como COMPLETO con la suma total
                    with transaction.atomic():
                        recibos_previos.delete()
                        self.tipo_pago = 'completo'
                        self.estado = 'pagado'
                        self.monto_pagado = monto_total
                        self.monto_cordobas = monto_total
                        self.concepto = f"{self.concepto} (consolidado)"
                        super().save(*args, **kwargs)
                    return
                else:
                    # Primer anticipo: debe ser MENOR al total
                    if Decimal(str(self.monto_pagado)) >= monto_total:
                        raise ValidationError(
                            "Si es anticipo, el monto debe ser menor al total del curso. "
                            "Para pagar todo use 'Completo'."
                        )
                    self.estado = 'anticipo'

            # COMPLETO: solo si no hay recibos previos
            elif self.tipo_pago == 'completo':
                if cantidad_previos > 0:
                    raise ValidationError(
                        "Ya existen anticipos para esta matrícula. Use otro anticipo para cerrar el saldo."
                    )
                self.estado = 'pagado'

        super().save(*args, **kwargs)

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
