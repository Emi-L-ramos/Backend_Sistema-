from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from rest_framework.authtoken.models import Token

from app_escuela.models import Estudiante, Matricula


class Command(BaseCommand):
    help = (
        'Desactiva estudiantes cuando han pasado '
        '24 horas desde la finalización por notas.'
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=(
                'Muestra qué estudiantes serían '
                'desactivados sin modificar datos.'
            ),
        )

    def handle(
        self,
        *args,
        **options,
    ):
        ahora = timezone.now()
        solo_revisar = options['dry_run']

        ids_estudiantes = list(
            Estudiante.objects
            .filter(
                activo=True,
                matriculas__fecha_desactivacion_usuario__isnull=False,
            )
            .values_list(
                'id',
                flat=True,
            )
            .distinct()
        )

        estudiantes_desactivados = 0
        usuarios_desactivados = 0
        estudiantes_omitidos = 0

        for estudiante_id in ids_estudiantes:
            with transaction.atomic():
                estudiante = (
                    Estudiante.objects
                    .select_for_update()
                    .get(id=estudiante_id)
                )

                tiene_matricula_activa = (
                    Matricula.objects
                    .filter(
                        estudiante=estudiante,
                    )
                    .exclude(
                        estado='finalizado',
                    )
                    .exists()
                )

                if tiene_matricula_activa:
                    estudiantes_omitidos += 1

                    self.stdout.write(
                        self.style.WARNING(
                            'Omitido: '
                            f'{estudiante.nombre} '
                            f'{estudiante.apellido}. '
                            'Tiene otra matrícula activa.'
                        )
                    )

                    continue

                ultima_desactivacion = (
                    Matricula.objects
                    .filter(
                        estudiante=estudiante,
                        fecha_desactivacion_usuario__isnull=False,
                    )
                    .aggregate(
                        ultima=Max(
                            'fecha_desactivacion_usuario'
                        )
                    )
                    .get('ultima')
                )

                if (
                    ultima_desactivacion is None
                    or ultima_desactivacion > ahora
                ):
                    continue

                usuarios = list(
                    estudiante.usuarios
                    .select_for_update()
                    .filter(
                        is_active=True,
                    )
                )

                if solo_revisar:
                    self.stdout.write(
                        self.style.WARNING(
                            'Se desactivaría: '
                            f'{estudiante.nombre} '
                            f'{estudiante.apellido}. '
                            f'Fecha vencida: '
                            f'{ultima_desactivacion}. '
                            f'Usuarios activos: '
                            f'{len(usuarios)}.'
                        )
                    )

                    continue

                ids_usuarios = [
                    usuario.id
                    for usuario in usuarios
                ]

                if ids_usuarios:
                    Token.objects.filter(
                        user_id__in=ids_usuarios,
                    ).delete()

                    estudiante.usuarios.filter(
                        id__in=ids_usuarios,
                    ).update(
                        is_active=False,
                    )

                    usuarios_desactivados += len(
                        ids_usuarios
                    )

                estudiante.activo = False

                estudiante.save(
                    update_fields=[
                        'activo',
                    ]
                )

                estudiantes_desactivados += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        'Desactivado: '
                        f'{estudiante.nombre} '
                        f'{estudiante.apellido}.'
                    )
                )

        if solo_revisar:
            self.stdout.write(
                self.style.WARNING(
                    'La revisión terminó sin modificar datos.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    'Proceso terminado. '
                    f'Estudiantes desactivados: '
                    f'{estudiantes_desactivados}. '
                    f'Usuarios desactivados: '
                    f'{usuarios_desactivados}. '
                    f'Estudiantes omitidos: '
                    f'{estudiantes_omitidos}.'
                )
            )