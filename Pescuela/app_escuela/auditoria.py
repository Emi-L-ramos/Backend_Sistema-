import logging

from rest_framework.authtoken.models import Token

from .models import RegistroAuditoria


logger = logging.getLogger(__name__)


MODULOS_POR_RUTA = {
    'roles': 'Configuración / Roles',
    'usuarios': 'Usuarios',
    'estudiantes': 'Estudiantes',
    'instructores': 'Instructores',
    'categorias': 'Configuración / Categorías',
    'plan-estudio': 'Plan de estudio',
    'valores-curso': 'Configuración / Valores de curso',
    'matricula': 'Matrículas',
    'recibo': 'Solvencia / Recibos',
    'calendario': 'Calendario',
    'asistencia': 'Asistencia',
    'notas': 'Notas',
    'progreso-tema': 'Progreso académico',
    'notificaciones': 'Notificaciones',
    'dashboard-plan': 'Plan de estudio',
    'preguntas-examen-teorico': 'Examen teórico',
    'examen-teorico': 'Examen teórico',
    'pagos-instructor': 'Configuración / Pago instructores',
    'cargos-institucionales': 'Configuración / Cargos',
    'certificados-egresados': 'Certificados',
    'configuracion-certificados': 'Certificados',
    'certificados-candidatos': 'Certificados',
    'certificados-guardados': 'Certificados',
    'certificados-generar': 'Certificados',
    'certificados': 'Certificados',
    'login': 'Seguridad',
    'logout': 'Seguridad',
}


ACCIONES_ESPECIALES = {
    'crear-bloque': 'Creó un bloque de clases',
    'crear-manual': 'Creó clases manualmente',
    'crear-examen': 'Programó un examen',
    'resultado-examen': 'Registró resultado de examen',
    'desactivar': 'Desactivó un registro',
    'reactivar': 'Reactivó un registro',
    'habilitar-marcado': 'Habilitó marcado de asistencia',
    'marcar': 'Marcó asistencia',
    'justificar': 'Justificó una asistencia',
    'finalizar-km': 'Finalizó kilometraje',
    'editar-km': 'Editó kilometraje',
    'imprimir': 'Preparó impresión de certificado',
    'imprimir-directo': 'Imprimió certificado',
    'imprimir-varios': 'Generó PowerPoint de certificados',
    'imprimir-varios-directo': 'Imprimió varios certificados',
}


ACCIONES_POR_METODO = {
    'POST': 'Creó un registro',
    'PUT': 'Editó un registro',
    'PATCH': 'Editó un registro',
    'DELETE': 'Eliminó un registro',
}


def obtener_ip(request):
    encabezado = request.META.get(
        'HTTP_X_FORWARDED_FOR',
        '',
    )

    if encabezado:
        return encabezado.split(',')[0].strip()

    return request.META.get('REMOTE_ADDR')


def obtener_usuario_desde_request(request):
    usuario = getattr(request, 'user', None)

    if usuario and getattr(usuario, 'is_authenticated', False):
        return usuario

    autorizacion = request.META.get(
        'HTTP_AUTHORIZATION',
        '',
    ).strip()

    if not autorizacion.lower().startswith('token '):
        return None

    clave = autorizacion.split(None, 1)[1].strip()

    if not clave:
        return None

    token = (
        Token.objects
        .select_related('user')
        .filter(key=clave)
        .first()
    )

    return token.user if token else None


def obtener_datos_ruta(request):
    partes = [
        parte
        for parte in request.path.strip('/').split('/')
        if parte
    ]

    # Ejemplo: /api/matricula/25/ -> ["api", "matricula", "25"]
    partes_api = partes[1:] if partes[:1] == ['api'] else partes

    recurso = partes_api[0] if partes_api else 'sistema'
    accion_ruta = (
        partes_api[-1]
        if len(partes_api) > 1
        else ''
    )

    referencia = ''

    for parte in partes_api[1:]:
        if parte.isdigit():
            referencia = parte
            break

    modulo = MODULOS_POR_RUTA.get(
        recurso,
        recurso.replace('-', ' ').title(),
    )

    accion = ACCIONES_ESPECIALES.get(
        accion_ruta,
        ACCIONES_POR_METODO.get(
            request.method,
            'Realizó una acción',
        ),
    )

    if referencia:
        detalle = (
            f'{accion} en {modulo}. '
            f'Registro #{referencia}.'
        )
    else:
        detalle = f'{accion} en {modulo}.'

    return {
        'accion': accion,
        'modulo': modulo,
        'detalle': detalle,
        'referencia': referencia,
    }


def registrar_auditoria(
    usuario,
    accion,
    modulo,
    detalle='',
    request=None,
    metodo='',
    ruta='',
    referencia='',
    estado_http=None,
):
    try:
        RegistroAuditoria.objects.create(
            usuario=usuario if usuario else None,
            usuario_nombre=(
                getattr(usuario, 'username', '')
                if usuario
                else ''
            ),
            accion=accion,
            modulo=modulo,
            detalle=detalle,
            metodo=metodo,
            ruta=ruta,
            referencia=str(referencia or ''),
            estado_http=estado_http,
            direccion_ip=(
                obtener_ip(request)
                if request
                else None
            ),
        )
    except Exception:
        # Un fallo en auditoría nunca debe bloquear
        # una matrícula, recibo u otra operación normal.
        logger.exception(
            'No se pudo registrar la auditoría.'
        )


class AuditoriaMiddleware:
    """
    Registra automáticamente solicitudes exitosas de modificación
    realizadas mediante API y TokenAuthentication.
    """

    METODOS_AUDITABLES = {
        'POST',
        'PUT',
        'PATCH',
        'DELETE',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = obtener_usuario_desde_request(request)

        response = self.get_response(request)

        if (
            request.method not in self.METODOS_AUDITABLES
            or not request.path.startswith('/api/')
            or request.path.startswith('/api/auditoria/')
            or not usuario
            or not (200 <= response.status_code < 400)
        ):
            return response

        datos = obtener_datos_ruta(request)

        registrar_auditoria(
            usuario=usuario,
            accion=datos['accion'],
            modulo=datos['modulo'],
            detalle=datos['detalle'],
            request=request,
            metodo=request.method,
            ruta=request.path,
            referencia=datos['referencia'],
            estado_http=response.status_code,
        )

        return response