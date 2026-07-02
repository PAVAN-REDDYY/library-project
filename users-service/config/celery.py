import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('users')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'users_queue'
app.autodiscover_tasks()
