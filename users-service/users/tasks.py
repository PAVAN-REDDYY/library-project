from config.celery import app


@app.task(name='users.tasks.apply_suspension')
def apply_suspension(user_id, is_suspended, reason):
    """Consumes the suspension decision made by rentals-service (it owns the
    overdue/suspension business rule since it owns BorrowRecord). This service
    just needs to keep its own UserProfile.is_suspended in sync so it displays
    correctly on the profile page.

    Idempotent-safe by construction: a redelivered call just sets the same
    fields again, no side-effect duplication risk.
    """
    from users.models import UserProfile

    try:
        profile = UserProfile.objects.get(user_id=user_id)
    except UserProfile.DoesNotExist:
        return
    profile.is_suspended = is_suspended
    profile.suspension_reason = reason
    profile.save()  # triggers the post_save signal above, which echoes the
                     # confirmed state back to rentals-service's cache - this
                     # is deliberate and terminates after one hop (upsert_user_cache
                     # is a plain upsert, it doesn't send anything further)
