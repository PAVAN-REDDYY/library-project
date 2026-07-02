import os
from pathlib import Path

from common.env import require_env

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = require_env('BOOKS_SECRET_KEY')

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
    'books',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    # No local User table here, so request.user comes entirely from the JWT
    # cookie/header (see common/jwt_auth.py) instead of
    # django.contrib.auth.middleware.AuthenticationMiddleware.
    'common.jwt_auth.JWTAuthenticationMiddleware',
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
                # Just reads whatever request.user already is (our
                # JWTAuthenticationMiddleware sets it) - doesn't require
                # django.contrib.auth's own AuthenticationMiddleware. Needed
                # so templates can use {{ user.is_authenticated }} directly.
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
            'NAME': os.environ.get('BOOKS_DB_NAME', 'books_db'),
            'USER': os.environ.get('DB_USER', 'root'),
            'PASSWORD': require_env('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }

AUTH_PASSWORD_VALIDATORS = []

# django.contrib.admin's system checks unconditionally require
# django.contrib.auth.middleware.AuthenticationMiddleware (or a subclass) to be
# present in MIDDLEWARE (admin.E408) - but this service has no local User
# table, so it deliberately uses common.jwt_auth.JWTAuthenticationMiddleware
# instead (see MIDDLEWARE above and common/admin_site.py). That middleware
# still populates request.user (with .is_staff etc., from the JWT), which is
# all JWTTrustingAdminSite.has_permission() actually needs at runtime - the
# check itself is a false positive for this architecture, not a real gap.
SILENCED_SYSTEM_CHECKS = ['admin.E408']

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Distinct per service: with no gateway, all three services sit on the same
# hostname (localhost) at different ports, and cookies are NOT port-scoped -
# same-named session/csrf cookies from different services would silently
# overwrite each other in the browser's cookie jar. Distinct names avoid that.
SESSION_COOKIE_NAME = 'books_sessionid'
CSRF_COOKIE_NAME = 'books_csrftoken'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'common.jwt_auth.JWTCookieAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# --- Cross-service contract -------------------------------------------------

# Must be identical across users-service/books-service/rentals-service.
JWT_SECRET = require_env('JWT_SECRET', hint='Must be identical across users-service/books-service/rentals-service.')

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672//')
CELERY_RESULT_BACKEND = None
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
# service run standalone (`manage.py runserver`) on its own port - see
# common/context_processors.py for why a root-relative path isn't enough.
USERS_SERVICE_PUBLIC_URL = os.environ.get('USERS_SERVICE_PUBLIC_URL', 'http://localhost:8001')
BOOKS_SERVICE_PUBLIC_URL = os.environ.get('BOOKS_SERVICE_PUBLIC_URL', 'http://localhost:8002')
RENTALS_SERVICE_PUBLIC_URL = os.environ.get('RENTALS_SERVICE_PUBLIC_URL', 'http://localhost:8003')

# No local login view in this service - @login_required must redirect to
# users-service's login page. Fully-qualified (not "/accounts/login/") because
# Django's redirect-to-login otherwise resolves against *this* service's own
# origin, which has no such path and would 404.
LOGIN_URL = f'{USERS_SERVICE_PUBLIC_URL}/accounts/login/'
