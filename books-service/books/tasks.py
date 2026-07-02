from django.db import transaction

from config.celery import app
from common.dispatch import send_task
from .models import Book, ReservationLog


@app.task(name='books.tasks.reserve_copy')
def reserve_copy(record_id, book_id):
    """rentals-service creates a BorrowRecord optimistically as 'pending' and
    calls this fire-and-forget to actually claim a copy against the
    authoritative stock count here. select_for_update makes the check-then-
    decrement atomic even under concurrent requests for the last copy."""
    with transaction.atomic():
        log, created = ReservationLog.objects.get_or_create(
            record_id=record_id, event_type='reserve', defaults={'book_id': book_id, 'outcome': ''},
        )
        if not created and log.outcome:
            # Already handled this record_id before (at-least-once redelivery) -
            # just re-send the same outcome, don't touch the stock count again.
            _notify_rentals(log.outcome, record_id, book_id)
            return

        book = Book.objects.select_for_update().get(pk=book_id)
        if book.available_copies > 0:
            book.available_copies -= 1
            book.save(update_fields=['available_copies', 'updated_at'])
            log.outcome = 'confirmed'
            log.save(update_fields=['outcome'])
            _notify_rentals('confirmed', record_id, book_id)
        else:
            log.outcome = 'rejected'
            log.save(update_fields=['outcome'])
            _notify_rentals('rejected', record_id, book_id)


def _notify_rentals(outcome, record_id, book_id):
    if outcome == 'confirmed':
        send_task(app, 'rentals.tasks.confirm_borrow', args=[record_id], queue='rentals_queue')
    else:
        send_task(
            app,
            'rentals.tasks.reject_borrow',
            args=[record_id, 'This book is currently out of stock.', book_id],
            queue='rentals_queue',
        )


@app.task(name='books.tasks.release_copy')
def release_copy(record_id, book_id):
    """Fire-and-forget from rentals-service on a return - can't logically fail,
    but still idempotency-guarded against redelivery."""
    with transaction.atomic():
        log, created = ReservationLog.objects.get_or_create(
            record_id=record_id, event_type='release', defaults={'book_id': book_id, 'outcome': 'confirmed'},
        )
        if not created:
            return
        book = Book.objects.select_for_update().get(pk=book_id)
        book.available_copies += 1
        book.save(update_fields=['available_copies', 'updated_at'])
