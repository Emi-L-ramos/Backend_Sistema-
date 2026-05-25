from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CargoInstitucional, Instructor, PagoInstructor, Rol, Usuario, Matricula, Recibo, Calendario, Estudiante, CategoriaVehiculo, PlanEstudio,Asistencia, Notas, ValorCurso 
from .models import TemaPlanEstudio, SubtemaPlanEstudio, Notificacion,ProgresoTema,HistorialPlanEstudio

from .models import PreguntaExamenTeorico,ExamenTeorico,RespuestaExamenTeorico,OpcionPreguntaExamenTeorico
# 1. Definimos cómo se verá el Usuario en el panel
class MiUsuarioAdmin(UserAdmin):
    # Esto añade el campo 'rol' a la edición del usuario
    fieldsets = UserAdmin.fieldsets + (
        ('Información de Escuela', {'fields': ('rol',)}),
    )
    # Esto añade el campo 'rol' al formulario de creación
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información de Escuela', {'fields': ('rol',)}),
    )
    list_display = ['username', 'email', 'rol', 'is_staff']

# 2. Registramos los modelos
admin.site.register(Matricula)
admin.site.register(Instructor)
admin.site.register(Recibo)
admin.site.register(Calendario)
admin.site.register(Rol)
admin.site.register(Estudiante)
admin.site.register(CategoriaVehiculo)
admin.site.register(PlanEstudio)
admin.site.register(Asistencia)
admin.site.register(Notas)
admin.site.register(TemaPlanEstudio)
admin.site.register(SubtemaPlanEstudio)
admin.site.register(Notificacion)
admin.site.register(ProgresoTema)
admin.site.register(HistorialPlanEstudio)

admin.site.register(PreguntaExamenTeorico)
admin.site.register(OpcionPreguntaExamenTeorico)
admin.site.register(ExamenTeorico)
admin.site.register(RespuestaExamenTeorico)
admin.site.register(PagoInstructor)
admin.site.register(CargoInstitucional)

# 3. Registro seguro del Usuario
try:
    admin.site.unregister(Usuario)
except:
    pass

admin.site.register(Usuario, MiUsuarioAdmin)

@admin.register(ValorCurso)
class ValorCursoAdmin(admin.ModelAdmin):
    list_display = (
        'tipo_curso',
        'precio_hora',
        'cantidad_horas',
        'precio_total',
        'activo',
        'fecha_modificacion'
    )

    list_filter = (
        'tipo_curso',
        'activo'
    )

    search_fields = (
        'tipo_curso',
    )