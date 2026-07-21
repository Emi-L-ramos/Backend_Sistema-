from datetime import datetime, time

from django.db import migrations
from django.utils import timezone


def convertir_fecha_calendario(fecha, hora=None):
    if not fecha:
        return None

    fecha_hora = datetime.combine(
        fecha,
        hora or time(23, 59, 59),
    )

    if timezone.is_naive(fecha_hora):
        fecha_hora = timezone.make_aware(
            fecha_hora,
            timezone.get_current_timezone(),
        )

    return fecha_hora


def completar_fechas_finalizacion(apps, schema_editor):
    Matricula = apps.get_model(
        'app_escuela',
        'Matricula',
    )

    Notas = apps.get_model(
        'app_escuela',
        'Notas',
    )

    Calendario = apps.get_model(
        'app_escuela',
        'Calendario',
    )

    matriculas_sin_fecha = (
        Matricula.objects
        .filter(
            estado='finalizado',
            fecha_finalizacion__isnull=True,
        )
        .only('id')
        .iterator(chunk_size=200)
    )

    for matricula in matriculas_sin_fecha:
        notas = Notas.objects.filter(
            matricula_id=matricula.id,
            tipo_nota__in=[
                'teorico',
                'practico',
            ],
        )

        tipos_notas = set(
            notas.values_list(
                'tipo_nota',
                flat=True,
            )
        )

        fecha_finalizacion = None

        if {
            'teorico',
            'practico',
        }.issubset(tipos_notas):
            fecha_finalizacion = (
                notas.order_by(
                    '-fecha_registro',
                    '-id',
                )
                .values_list(
                    'fecha_registro',
                    flat=True,
                )
                .first()
            )

        if not fecha_finalizacion:
            examen_policial = (
                Calendario.objects
                .filter(
                    matricula_id=matricula.id,
                    es_examen=True,
                    estado='completada',
                )
                .order_by(
                    '-fecha',
                    '-hora_fin',
                    '-id',
                )
                .first()
            )

            if examen_policial:
                fecha_finalizacion = (
                    convertir_fecha_calendario(
                        examen_policial.fecha,
                        examen_policial.hora_fin,
                    )
                )

        if not fecha_finalizacion:
            ultima_clase = (
                Calendario.objects
                .filter(
                    matricula_id=matricula.id,
                    es_examen=False,
                )
                .exclude(
                    estado='cancelada',
                )
                .order_by(
                    '-fecha',
                    '-hora_fin',
                    '-id',
                )
                .first()
            )

            if ultima_clase:
                fecha_finalizacion = (
                    convertir_fecha_calendario(
                        ultima_clase.fecha,
                        ultima_clase.hora_fin,
                    )
                )

        if fecha_finalizacion:
            Matricula.objects.filter(
                id=matricula.id,
                fecha_finalizacion__isnull=True,
            ).update(
                fecha_finalizacion=fecha_finalizacion
            )


def no_revertir_fechas(apps, schema_editor):
    """
    No se borran las fechas al revertir porque podrían
    mezclarse con fechas nuevas registradas en producción.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        (
            'app_escuela',
            '0020_matricula_fecha_finalizacion',
        ),
    ]

    operations = [
        migrations.RunPython(
            completar_fechas_finalizacion,
            no_revertir_fechas,
        ),
    ]