import os
from pathlib import Path

from common.env import require_env

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = require_env('USERS_SECRET_KEY')

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',

    # This service
    'users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'common.context_processors.service_urls',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

if os.environ.get('USE_SQLITE', '1') == '1':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # SQLite's file locking is weak under concurrent writers (this
            # service's web process plus its Celery worker hitting the same
            # file) - a longer busy-timeout makes a second writer retry
            # instead of immediately raising "database is locked".
            'OPTIONS': {'timeout': 20},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('USERS_DB_NAME', 'users_db'),
            'USER': os.environ.get('DB_USER', 'root'),
            'PASSWORD': require_env('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# users-service keeps real Django session auth (it's the only service with a
# local password store) - LOGIN_URL is local, but redirect targets after
# login/logout point at rentals-service's home page, which lives in a
# different service, so those are set as hardcoded absolute paths in
# users/views.py rather than through this setting.
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Distinct per service: with no gateway, all three services sit on the same
# hostname (localhost) at different ports, and cookies are NOT port-scoped -
# same-named session/csrf cookies from different services would silently
# overwrite each other in the browser's cookie jar. Distinct names avoid that.
SESSION_COOKIE_NAME = 'users_sessionid'
CSRF_COOKIE_NAME = 'users_csrftoken'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# --- Cross-service contract -------------------------------------------------

# Must be identical across users-service/books-service/rentals-service - this
# is the shared HS256 signing key from common/jwt_auth.py. users-service is
# the only service that *encodes* tokens; the other two only *decode*.
JWT_SECRET = require_env('JWT_SECRET', hint='Must be identical across users-service/books-service/rentals-service.')

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672//')
CELERY_RESULT_BACKEND = None
# Fire-and-forget tasks only (nothing here ever waits on a return value), and
# defaulting to eager keeps this service fully runnable standalone (tests,
# `manage.py runserver`) with no broker present. Whatever deployment wires up
# a real broker should set this to "0".
CELERY_TASK_ALWAYS_EAGER = os.environ.get('CELERY_TASK_ALWAYS_EAGER', '1') == '1'

# kombu's built-in filesystem transport - a real broker (messages actually
# cross process boundaries via a shared directory) with no server to install.
# Only relevant when CELERY_BROKER_URL=filesystem://, which is what a plain
# `manage.py runserver`/`celery worker` local run uses since there's no
# RabbitMQ/Redis here (that's a deployment concern, not this service's).
CELERY_BROKER_TRANSPORT_OPTIONS = {}
if CELERY_BROKER_URL.startswith('filesystem://'):
    # Shared across all three services (repo root, not this service's own
    # BASE_DIR) - that's the whole point of a filesystem "broker".
    _broker_dir = os.environ.get('CELERY_FILESYSTEM_BROKER_DIR', str(BASE_DIR.parent / '.dev_broker'))
    os.makedirs(_broker_dir, exist_ok=True)
    os.makedirs(os.path.join(_broker_dir, 'processed'), exist_ok=True)
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        'data_folder_in': _broker_dir,
        'data_folder_out': _broker_dir,
        'data_folder_processed': os.path.join(_broker_dir, 'processed'),
    }

# Fully-qualified so cross-service template links/redirects work with each
# service just run standalone (`manage.py runserver`) on its own port - see
# common/context_processors.py for why a root-relative path isn't enough.
USERS_SERVICE_PUBLIC_URL = os.environ.get('USERS_SERVICE_PUBLIC_URL', 'http://localhost:8001')
BOOKS_SERVICE_PUBLIC_URL = os.environ.get('BOOKS_SERVICE_PUBLIC_URL', 'http://localhost:8002')
RENTALS_SERVICE_PUBLIC_URL = os.environ.get('RENTALS_SERVICE_PUBLIC_URL', 'http://localhost:8003')
