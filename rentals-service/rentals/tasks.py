from django.db.models import F
from config.celery import app
from common.dispatch import send_task


# ---- Producers: this service telling another service to do something (fire-and-forget) ----

def send_reserve_copy(record_id, book_id):
    send_task(app, 'books.tasks.reserve_copy', args=[record_id, book_id], queue='books_queue')


def send_release_copy(record_id, book_id):
    send_task(app, 'books.tasks.release_copy', args=[record_id, book_id], queue='books_queue')


def send_apply_suspension(user_id, is_suspended, reason):
    send_task(app, 'users.tasks.apply_suspension', args=[user_id, is_suspended, reason], queue='users_queue')


# ---- Consumers: another service telling this service something happened ----

@app.task(name='rentals.tasks.upsert_book_cache')
def upsert_book_cache(book_id, title, author, available_copies, total_copies):
    from .models import BookCache
    BookCache.objects.update_or_create(
        book_id=book_id,
        defaults={'title': title, 'author': author, 'available_copies': available_copies, 'total_copies': total_copies},
    )


@app.task(name='rentals.tasks.upsert_user_cache')
def upsert_user_cache(user_id, username, is_suspended):
    from .models import UserCache
    UserCache.objects.update_or_create(
        user_id=user_id, defaults={'username': username, 'is_suspended': is_suspended},
    )


@app.task(name='rentals.tasks.confirm_borrow')
def confirm_borrow(record_id):
    from .models import BorrowRecord
    # Conditional update, not get()+save(): naturally idempotent against
    # at-least-once redelivery - a second delivery finds status already
    # ACTIVE (not PENDING), matches zero rows, no-ops.
    BorrowRecord.objects.filter(id=record_id, status=BorrowRecord.Status.PENDING).update(
        status=BorrowRecord.Status.ACTIVE,
    )


@app.task(name='rentals.tasks.reject_borrow')
def reject_borrow(record_id, reason, book_id):
    from .models import BorrowRecord, BookCache
    updated = BorrowRecord.objects.filter(id=record_id, status=BorrowRecord.Status.PENDING).update(
        status=BorrowRecord.Status.REJECTED, reject_reason=reason, active_loan_key=None,
    )
    if updated:
        # Restore the optimistic decrement made in borrow_book() - without
        # this, BookCache drifts permanently low after every lost race. The
        # `if updated:` guard also makes this idempotent: a redelivery finds
        # the record already REJECTED, updated == 0, so we don't double-credit.
        BookCache.objects.filter(book_id=book_id).update(available_copies=F('available_copies') + 1)
