from django.db.models.signals import post_save
from django.dispatch import receiver

from config.celery import app as celery_app
from common.dispatch import send_task
from .models import Book


@receiver(post_save, sender=Book)
def sync_book_cache(sender, instance, **kwargs):
    send_task(
        celery_app,
        'rentals.tasks.upsert_book_cache',
        args=[instance.id, instance.title, instance.author, instance.available_copies, instance.total_copies],
        queue='rentals_queue',
    )
