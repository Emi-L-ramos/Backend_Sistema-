# Generated manually for historical theoretical exam attempts.

from django.db import migrations, models
from django.utils import timezone


def crear_intentos_historicos(apps, schema_editor):
    """
    Crea intentos históricos para los exámenes existentes.

    En la estructura anterior, las respuestas estaban ligadas
    directamente al examen y no a un intento. Esta migración
    crea el intento 1 para cada examen que ya tenga respuestas,
    nota o estado habilitado/realizado.
    """

    ExamenTeorico = apps.get_model(
        'app_escuela',
        'ExamenTeorico',
    )

    IntentoExamenTeorico = apps.get_model(
        'app_escuela',
        'IntentoExamenTeorico',
    )

    PreguntaIntentoExamenTeorico = apps.get_model(
        'app_escuela',
        'PreguntaIntentoExamenTeorico',
    )

    RespuestaExamenTeorico = apps.get_model(
        'app_escuela',
        'RespuestaExamenTeorico',
    )

    base_datos = schema_editor.connection.alias
    ahora = timezone.now()

    examenes = (
        ExamenTeorico.objects
        .using(base_datos)
        .all()
        .iterator()
    )

    for examen in examenes:
        respuestas = list(
            RespuestaExamenTeorico.objects
            .using(base_datos)
            .filter(
                examen_id=examen.id
            )
            .order_by('id')
        )

        tiene_respuestas = bool(respuestas)

        tiene_resultado = bool(
            examen.estado == 'realizado'
            or examen.nota is not None
            or tiene_respuestas
        )

        esta_habilitado = (
            examen.estado == 'habilitado'
        )

        if not tiene_resultado and not esta_habilitado:
            continue

        estado_intento = (
            'realizado'
            if tiene_resultado
            else 'habilitado'
        )

        fecha_habilitado = (
            examen.fecha_habilitado
            or examen.fecha_realizado
            or ahora
        )

        intento, _ = (
            IntentoExamenTeorico.objects
            .using(base_datos)
            .get_or_create(
                examen_id=examen.id,
                numero_intento=1,
                defaults={
                    'estado': estado_intento,
                    'nota': examen.nota,
                    'fecha_habilitado': fecha_habilitado,
                    'fecha_iniciado': (
                        fecha_habilitado
                        if tiene_respuestas
                        else None
                    ),
                    'fecha_realizado': (
                        examen.fecha_realizado
                        if tiene_resultado
                        else None
                    ),
                },
            )
        )

        preguntas_procesadas = {}
        siguiente_orden = 1

        for respuesta in respuestas:
            pregunta_id = respuesta.pregunta_id

            respuesta_anterior_id = (
                preguntas_procesadas.get(
                    pregunta_id
                )
            )

            if respuesta_anterior_id:
                (
                    RespuestaExamenTeorico.objects
                    .using(base_datos)
                    .filter(
                        id=respuesta_anterior_id
                    )
                    .delete()
                )
            else:
                (
                    PreguntaIntentoExamenTeorico.objects
                    .using(base_datos)
                    .get_or_create(
                        intento_id=intento.id,
                        pregunta_id=pregunta_id,
                        defaults={
                            'orden': siguiente_orden,
                        },
                    )
                )

                siguiente_orden += 1

            respuesta.intento_id = intento.id

            respuesta.save(
                using=base_datos,
                update_fields=[
                    'intento',
                ],
            )

            preguntas_procesadas[
                pregunta_id
            ] = respuesta.id


def revertir_intentos_historicos(apps, schema_editor):
    """
    Desvincula las respuestas de los intentos antes de
    revertir esta migración.
    """

    IntentoExamenTeorico = apps.get_model(
        'app_escuela',
        'IntentoExamenTeorico',
    )

    PreguntaIntentoExamenTeorico = apps.get_model(
        'app_escuela',
        'PreguntaIntentoExamenTeorico',
    )

    RespuestaExamenTeorico = apps.get_model(
        'app_escuela',
        'RespuestaExamenTeorico',
    )

    base_datos = schema_editor.connection.alias

    (
        RespuestaExamenTeorico.objects
        .using(base_datos)
        .update(
            intento_id=None
        )
    )

    (
        PreguntaIntentoExamenTeorico.objects
        .using(base_datos)
        .all()
        .delete()
    )

    (
        IntentoExamenTeorico.objects
        .using(base_datos)
        .all()
        .delete()
    )


class Migration(migrations.Migration):

    dependencies = [
        (
            'app_escuela',
            '0017_historial_intentos_examen',
        ),
    ]

    operations = [
        migrations.RunPython(
            crear_intentos_historicos,
            revertir_intentos_historicos,
        ),
        migrations.AddConstraint(
            model_name='respuestaexamenteorico',
            constraint=models.UniqueConstraint(
                fields=[
                    'intento',
                    'pregunta',
                ],
                name='respuesta_unica_por_intento',
            ),
        ),
    ]