import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('rentals')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'rentals_queue'
app.autodiscover_tasks()
