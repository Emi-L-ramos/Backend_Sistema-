from rest_framework.permissions import BasePermission


ROLES_ADMINISTRATIVOS = frozenset({
    'admin',
    'administrador',
    'secretaria',
})

ROL_INSTRUCTOR = 'instructor'
ROL_ESTUDIANTE = 'estudiante'


def normalizar_rol(valor):
    """
    Devuelve el nombre del rol sin espacios y en minúsculas.
    """
    return str(valor or '').strip().lower()


def obtener_rol_usuario(user):
    """
    Obtiene de forma segura el rol normalizado del usuario.
    """
    if not user or not getattr(
        user,
        'is_authenticated',
        False
    ):
        return ''

    return normalizar_rol(
        getattr(user, 'rol_nombre', '')
    )


def es_administrativo(user):
    """
    Reconoce Administrador, Administración,
    Secretaría, usuarios staff y superusuarios.
    """
    if not user or not getattr(
        user,
        'is_authenticated',
        False
    ):
        return False

    return bool(
        getattr(user, 'is_superuser', False)
        or getattr(user, 'is_staff', False)
        or obtener_rol_usuario(user)
        in ROLES_ADMINISTRATIVOS
    )


def es_instructor(user):
    """
    Comprueba que el usuario tenga el rol Instructor
    y que esté relacionado con un instructor.
    """
    if not user or not getattr(
        user,
        'is_authenticated',
        False
    ):
        return False

    return bool(
        obtener_rol_usuario(user) == ROL_INSTRUCTOR
        and getattr(user, 'instructor_id', None)
    )


def es_estudiante(user):
    """
    Comprueba que el usuario tenga el rol Estudiante
    y que esté relacionado con un estudiante.
    """
    if not user or not getattr(
        user,
        'is_authenticated',
        False
    ):
        return False

    return bool(
        obtener_rol_usuario(user) == ROL_ESTUDIANTE
        and getattr(user, 'estudiante_id', None)
    )


def tiene_alguno_de_los_roles(user, *roles):
    """
    Comprueba roles normalizados sin repetir
    comparaciones dentro de las vistas.
    """
    roles_normalizados = {
        normalizar_rol(rol)
        for rol in roles
        if normalizar_rol(rol)
    }

    return (
        obtener_rol_usuario(user)
        in roles_normalizados
    )


class EsAdministrativo(BasePermission):
    message = (
        'Esta acción está permitida únicamente para '
        'Administración o Secretaría.'
    )

    def has_permission(self, request, view):
        return es_administrativo(request.user)


class EsInstructor(BasePermission):
    message = (
        'Esta acción está permitida únicamente '
        'para instructores.'
    )

    def has_permission(self, request, view):
        return es_instructor(request.user)


class EsEstudiante(BasePermission):
    message = (
        'Esta acción está permitida únicamente '
        'para estudiantes.'
    )

    def has_permission(self, request, view):
        return es_estudiante(request.user)


class EsAdministrativoOInstructor(BasePermission):
    message = (
        'Esta acción está permitida únicamente para '
        'Administración, Secretaría o instructores.'
    )

    def has_permission(self, request, view):
        return bool(
            es_administrativo(request.user)
            or es_instructor(request.user)
        )


class EsAdministrativoOEstudiante(BasePermission):
    message = (
        'Esta acción está permitida únicamente para '
        'Administración, Secretaría o estudiantes.'
    )

    def has_permission(self, request, view):
        return bool(
            es_administrativo(request.user)
            or es_estudiante(request.user)
        )


class EsUsuarioDelSistema(BasePermission):
    message = (
        'El usuario no tiene un rol válido '
        'dentro del sistema.'
    )

    def has_permission(self, request, view):
        return bool(
            es_administrativo(request.user)
            or es_instructor(request.user)
            or es_estudiante(request.user)
        )