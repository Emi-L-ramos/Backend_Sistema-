from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Instructor, Usuario
from .models import Matricula
from .models import Recibo


admin.site.register(Matricula)
admin.site.register(Usuario, UserAdmin)
admin.site.register(Instructor)
admin.site.register(Recibo)

