from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(post_save, sender=UserProfile)
def sync_user_cache(sender, instance, **kwargs):
    """Fire-and-forget push of this user's cache row to rentals-service, which
    maintains a local read-model cache of every user's is_suspended flag for
    its own borrow-eligibility checks (it can't call back into this service's
    DB synchronously - services don't share a database in this split).

    Fires both on registration (profile just created) and whenever suspension
    state changes (see tasks.apply_suspension), which are exactly the two
    cases where rentals-service's cache needs refreshing.
    """
    from config.celery import app as celery_app
    from common.dispatch import send_task

    # send_task() addresses a task by name only (there's no local
    # `rentals.tasks.upsert_user_cache` object registered in this process, it
    # lives in rentals-service), so unlike a locally-registered @app.task,
    # CELERY_TASK_ALWAYS_EAGER has no effect on it - common.dispatch.send_task
    # is a thin wrapper that skips the real broker call when running eager
    # (the default, so this service works standalone with no broker present).
    try:
        send_task(
            celery_app,
            'rentals.tasks.upsert_user_cache',
            args=[instance.user_id, instance.user.username, instance.is_suspended],
            queue='rentals_queue',
        )
    except Exception:
        # True fire-and-forget: a broker hiccup must never break a user/profile
        # save. rentals-service's cache will simply catch up on the next write
        # or its own periodic reconciliation, if any.
        pass
