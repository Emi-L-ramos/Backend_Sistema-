from django.db import migrations, models


def completar_dias_programados(
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

    for matricula in (
        Matricula.objects
        .all()
        .iterator()
    ):
        modalidad = str(
            matricula.modalidad or ''
        ).strip().lower()

        if modalidad == 'regular':
            dias = [
                0,
                1,
                2,
                3,
                4,
            ]
        elif modalidad == 'extraordinario':
            dias = [
                5,
                6,
            ]
        else:
            fechas = (
                Calendario.objects
                .filter(
                    matricula_id=matricula.id,
                    es_examen=False,
                )
                .exclude(
                    estado='cancelada'
                )
                .values_list(
                    'fecha',
                    flat=True,
                )
            )

            dias = sorted({
                fecha.weekday()
                for fecha in fechas
                if fecha
            })

        matricula.dias_programados = dias

        matricula.save(
            update_fields=[
                'dias_programados',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            'app_escuela',
            '0024_remove_notificacion_notificacion_unica_por_tema_tipo_and_more',
        ),
    ]

    operations = [
        migrations.AddField(
            model_name='matricula',
            name='dias_programados',
            field=models.JSONField(
                blank=True,
                default=list,
            ),
        ),
        migrations.RunPython(
            completar_dias_programados,
            migrations.RunPython.noop,
        ),
    ]