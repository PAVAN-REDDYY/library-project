import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('books')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'books_queue'
app.autodiscover_tasks()
