from django.db import migrations, models


def completar_fechas_programadas(
    apps,
    schema_editor,
):
    Matricula = apps.get_model(
        'app_escuela',
        'Matricula',
    )

    Calendario = apps.get_model(
        'app_escuela',
        'Calendario',
    )

    matriculas_mixtas = (
        Matricula.objects
        .filter(
            modalidad__iexact='Mixto',
        )
        .iterator()
    )

    for matricula in matriculas_mixtas:
        fechas = list(
            Calendario.objects
            .filter(
                matricula_id=matricula.id,
                es_examen=False,
            )
            .exclude(
                estado='cancelada',
            )
            .order_by(
                'numero_clase',
                'fecha',
                'hora_inicio',
                'id',
            )
            .values_list(
                'fecha',
                flat=True,
            )
        )

        matricula.fechas_programadas = [
            fecha.isoformat()
            for fecha in fechas
            if fecha
        ]

        matricula.save(
            update_fields=[
                'fechas_programadas',
            ]
        )


def limpiar_fechas_programadas(
    apps,
    schema_editor,
):
    Matricula = apps.get_model(
        'app_escuela',
        'Matricula',
    )

    Matricula.objects.update(
        fechas_programadas=[],
    )


class Migration(migrations.Migration):

    dependencies = [
        (
            'app_escuela',
            '0025_matricula_dias_programados',
        ),
    ]

    operations = [
        migrations.AddField(
            model_name='matricula',
            name='fechas_programadas',
            field=models.JSONField(
                blank=True,
                default=list,
            ),
        ),
        migrations.RunPython(
            completar_fechas_programadas,
            limpiar_fechas_programadas,
        ),
    ]