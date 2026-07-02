from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from datetime import timedelta

from .models import BorrowRecord, BookCache, UserCache, BORROW_DAYS, EXTENSION_DAYS, MAX_BORROWS
from . import tasks

_ACTIVE = [BorrowRecord.Status.PENDING, BorrowRecord.Status.ACTIVE, BorrowRecord.Status.EXTENDED, BorrowRecord.Status.OVERDUE]


def check_overdue_and_suspend(user_id):
    """Scans this user's in-flight records, flips any past-due ones to
    OVERDUE, then updates the LOCAL UserCache.is_suspended flag (this service
    computes and owns this decision) and only THEN notifies users-service so
    its own copy (used for the profile page) eventually matches. Order
    matters: local write first, network notify second - if a crash happens
    between the two, this service's own gating logic is still correct; only
    users-service's display would be briefly stale, which is an acceptable,
    self-healing eventual-consistency window."""
    today = timezone.now().date()

    in_flight = BorrowRecord.objects.filter(
        user_id=user_id, status__in=[BorrowRecord.Status.ACTIVE, BorrowRecord.Status.EXTENDED],
    )
    for record in in_flight:
        if record.effective_due_date < today:
            record.status = BorrowRecord.Status.OVERDUE
            record.save(update_fields=['status', 'updated_at'])

    has_overdue = BorrowRecord.objects.filter(user_id=user_id, status=BorrowRecord.Status.OVERDUE).exists()

    user_cache, _ = UserCache.objects.get_or_create(user_id=user_id, defaults={'username': '', 'is_suspended': False})
    if has_overdue and not user_cache.is_suspended:
        user_cache.is_suspended = True
        user_cache.save(update_fields=['is_suspended', 'updated_at'])
        tasks.send_apply_suspension(
            user_id, True,
            'Account suspended: one or more borrowed books are overdue. '
            'Return the book or request an extension to restore access.',
        )
    elif not has_overdue and user_cache.is_suspended:
        user_cache.is_suspended = False
        user_cache.save(update_fields=['is_suspended', 'updated_at'])
        tasks.send_apply_suspension(user_id, False, '')

    return has_overdue


def can_borrow(user_id, book_id):
    """Returns (allowed: bool, reason: str | None). Reads only LOCAL caches -
    no network call, so this is always fast even though the check is against
    eventually-consistent data. The DB UniqueConstraint on BorrowRecord and
    books-service's authoritative select_for_update (see reserve_copy) are
    the real correctness backstops for the rare race this optimism misses."""
    check_overdue_and_suspend(user_id)

    user_cache = UserCache.objects.filter(user_id=user_id).first()
    if user_cache and user_cache.is_suspended:
        return False, (
            'Your account is suspended due to an overdue book. '
            'Return the overdue book or request a 7-day extension to restore borrowing.'
        )

    active_count = BorrowRecord.objects.filter(user_id=user_id, status__in=_ACTIVE).count()
    if active_count >= MAX_BORROWS:
        return False, f'You have reached the {MAX_BORROWS}-book limit. Return a book before borrowing another.'

    book_cache = BookCache.objects.filter(book_id=book_id).first()
    if not book_cache or book_cache.available_copies <= 0:
        return False, 'This book is currently out of stock. Check back soon.'

    already = BorrowRecord.objects.filter(user_id=user_id, book_id=book_id, status__in=_ACTIVE).exists()
    if already:
        return False, 'You already have this book on loan.'

    return True, None


def borrow_book(user_id, book_id):
    """Creates a PENDING record and optimistically decrements the local cache
    count (both in one local DB transaction, so they move together
    atomically), then fires reserve_copy at books-service fire-and-forget to
    actually claim the copy against the authoritative count there. Raises
    ValueError on failure (including the rare UniqueConstraint race - two
    near-simultaneous borrow attempts for the same user+book)."""
    ok, error = can_borrow(user_id, book_id)
    if not ok:
        raise ValueError(error)

    today = timezone.now().date()
    try:
        with transaction.atomic():
            record = BorrowRecord.objects.create(
                user_id=user_id, book_id=book_id,
                borrow_date=today, due_date=today + timedelta(days=BORROW_DAYS),
                status=BorrowRecord.Status.PENDING,
                active_loan_key=f'{user_id}:{book_id}',
            )
            BookCache.objects.filter(book_id=book_id).update(available_copies=F('available_copies') - 1)
    except IntegrityError:
        raise ValueError('You already have this book on loan.')

    tasks.send_reserve_copy(record.id, book_id)
    return record


def return_book(record):
    if record.status == BorrowRecord.Status.RETURNED:
        raise ValueError('This book has already been returned.')

    record.return_date = timezone.now().date()
    record.status = BorrowRecord.Status.RETURNED
    record.active_loan_key = None
    record.save()

    tasks.send_release_copy(record.id, record.book_id)
    check_overdue_and_suspend(record.user_id)
    return record


def extend_borrow(record):
    if record.extended:
        raise ValueError('This borrow has already been extended. No further extensions are allowed.')
    if record.status in [BorrowRecord.Status.RETURNED, BorrowRecord.Status.PENDING, BorrowRecord.Status.REJECTED]:
        raise ValueError('Cannot extend this record.')

    record.extended = True
    record.extended_due_date = record.due_date + timedelta(days=EXTENSION_DAYS)
    record.status = BorrowRecord.Status.EXTENDED
    record.save()

    check_overdue_and_suspend(record.user_id)
    return record
