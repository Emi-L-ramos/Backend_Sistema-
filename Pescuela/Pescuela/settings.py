"""
Django settings for Pescuela project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv  # 1. Importa la función
load_dotenv()  # 2. Carga las variables del archivo .env

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-5zz7xfden4ks^m$1m!ggx6%&(74o(g9#rw8dtg^*cx(-zult-!'

# SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG') == 'True'
# ✅ AGREGAR localhost y 127.0.0.1 para desarrollo


ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "backendsistema-production.up.railway.app",
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'rest_framework.authtoken',  # ✅ Token authentication
    
    'app_escuela',  # Tu aplicación
    'django_filters',  # ✅ Para filtrado en vistas
]


# ASGI_APPLICATION = 'Pescuela.asgi.application'

# # Para desarrollo (memoria)
# CHANNEL_LAYERS = {
#     'default': {
#         'BACKEND': 'channels.layers.InMemoryChannelLayer',
#     }
# }
# # ✅ Modelo de usuario personalizado


# Para producción (Redis - descomentar si tienes Redis)
# CHANNEL_LAYERS = {
#     'default': {
#         'BACKEND': 'channels_redis.core.RedisChannelLayer',
#         'CONFIG': {
#             "hosts": [('127.0.0.1', 6379)],
#         },
#     },
# }
AUTH_USER_MODEL = 'app_escuela.Usuario'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # ✅ CORS debe ir aquí
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

# Database
#DATABASES = {
#    'default': {
#       'ENGINE': 'django.db.backends.mysql',
#        'NAME': 'adiact_bd',
#       'USER': 'root',
#        'PASSWORD': '',  # XAMPP por defecto no tiene contraseña
#         'HOST': 'localhost',
#          'HOST': 'localhost',
#          'PORT': '3306',
#          'OPTIONS': {
#              'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
#              'charset': 'utf8mb4',
#          }
#      }
#  }


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('MYSQL_DATABASE', 'defaultdb'),
        'USER': os.environ.get('MYSQL_USER', 'avnadmin'),
        'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
        'HOST': os.environ.get('MYSQL_HOST', ''),
        'PORT': os.environ.get('MYSQL_PORT', '22815'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
            'ssl': {},
        }
    }
}

# ✅ CORS - Permitir frontend
CORS_ALLOWED_ORIGINS = [
    "https://frontend-sistema-dgmt.vercel.app",
    "http://127.0.0.1:5173",
    "http://localhost:5173", # Del incoming
    
]

CSRF_TRUSTED_ORIGINS = [
    "https://backendsistema-production.up.railway.app",
    "https://frontend-sistema-dgmt.vercel.app",
]

# ✅ Opcional: Permitir credenciales
CORS_ALLOW_CREDENTIALS = True

# ✅ Métodos permitidos
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# ✅ Headers permitidos
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

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 6,  # ✅ Mínimo 6 caracteres
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-es'  # ✅ Cambiar a español
TIME_ZONE = 'America/Managua'  # ✅ Cambiar a tu zona horaria (Nicaragua)
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # ✅ Para producción

# Media files (subidas de usuarios)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ✅ REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],
}

# ✅ Configuración de logging (opcional, para depuración)
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