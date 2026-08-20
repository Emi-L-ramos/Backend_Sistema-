"""
Django settings for Pescuela project.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def obtener_variable_obligatoria(nombre):
    valor = os.environ.get(nombre)

    if valor is None or not valor.strip():
        raise ImproperlyConfigured(
            f"La variable de entorno {nombre} es obligatoria."
        )

    return valor.strip()


def obtener_lista_entorno(nombre, valor_predeterminado=""):
    valor = os.environ.get(nombre, valor_predeterminado)

    return [
        elemento.strip()
        for elemento in valor.split(",")
        if elemento.strip()
    ]

SECRET_KEY = obtener_variable_obligatoria("SECRET_KEY")

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = obtener_lista_entorno(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1"
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',

    'app_escuela',
]

AUTH_USER_MODEL = 'app_escuela.Usuario'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Pescuela.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'Pescuela.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('MYSQL_DATABASE') or os.environ.get(
            'DB_NAME',
            'adiact_bd'
        ),
        'USER': os.environ.get('MYSQL_USER') or os.environ.get(
            'DB_USER',
            'adiact_user'
        ),
        'PASSWORD': os.environ.get('MYSQL_PASSWORD') or os.environ.get(
            'DB_PASSWORD',
            ''
        ),
        'HOST': os.environ.get('MYSQL_HOST') or os.environ.get(
            'DB_HOST',
            '127.0.0.1'
        ),
        'PORT': os.environ.get('MYSQL_PORT') or os.environ.get(
            'DB_PORT',
            '3306'
        ),
        'CONN_MAX_AGE': int(
            os.environ.get('MYSQL_CONN_MAX_AGE', '60')
        ),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        }
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': os.environ.get('DB_NAME', 'adiact_bd'),      # Cambiado a DB_NAME
#         'USER': os.environ.get('DB_USER', 'root'),           # Cambiado a DB_USER
#         'PASSWORD': os.environ.get('DB_PASSWORD', ''),       # Cambiado a DB_PASSWORD
#         'HOST': os.environ.get('DB_HOST', '127.0.0.1'),      # Cambiado a DB_HOST
#         'PORT': os.environ.get('DB_PORT', '3306'),           # Cambiado a DB_PORT
#         'CONN_MAX_AGE': int(
#             os.environ.get('MYSQL_CONN_MAX_AGE', '60')
#         ),
#         'CONN_HEALTH_CHECKS': True,
#         'OPTIONS': {
#             'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
#             'charset': 'utf8mb4',
#         }
#     }
# }



CORS_ALLOWED_ORIGINS = obtener_lista_entorno(
    "CORS_ALLOWED_ORIGINS",
    (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://esesaemca.cloud,"
        "https://www.esesaemca.cloud"
    )
)

CSRF_TRUSTED_ORIGINS = obtener_lista_entorno(
    "CSRF_TRUSTED_ORIGINS",
    (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://esesaemca.cloud,"
        "https://www.esesaemca.cloud"
    )
)

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'MinimumLengthValidator'
        ),
        'OPTIONS': {
            'min_length': 10,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Managua'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'login': os.environ.get(
            'LOGIN_THROTTLE_RATE',
            '5/minute'
        ),
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
}

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_HSTS_SECONDS = int(
        os.environ.get(
            'SECURE_HSTS_SECONDS',
            '0'
        )
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = (
        SECURE_HSTS_SECONDS > 0
    )
    SECURE_HSTS_PRELOAD = (
        SECURE_HSTS_SECONDS > 0
    )

LIBREOFFICE_BIN = r"C:\Program Files\LibreOffice\program\soffice.exe"