from django.utils import timezone
from datetime import timedelta
from .models import BorrowRecord, BORROW_DAYS, EXTENSION_DAYS, MAX_BORROWS

_ACTIVE = [BorrowRecord.Status.ACTIVE, BorrowRecord.Status.EXTENDED, BorrowRecord.Status.OVERDUE]


def check_overdue_and_suspend(user):
    """
    Scan the user's active records. Mark any past-due records as OVERDUE, then
    suspend or unsuspend the account based on whether any OVERDUE records exist.
    Returns True if the account is (or remains) suspended after the check.
    """
    today = timezone.now().date()

    in_flight = BorrowRecord.objects.filter(
        user=user,
        status__in=[BorrowRecord.Status.ACTIVE, BorrowRecord.Status.EXTENDED],
    )
    for record in in_flight:
        if record.effective_due_date < today:
            record.status = BorrowRecord.Status.OVERDUE
            record.save(update_fields=['status', 'updated_at'])

    has_overdue = BorrowRecord.objects.filter(
        user=user, status=BorrowRecord.Status.OVERDUE
    ).exists()

    profile = user.profile
    if has_overdue and not profile.is_suspended:
        profile.is_suspended = True
        profile.suspension_reason = (
            'Account suspended: one or more borrowed books are overdue. '
            'Return the book or request an extension to restore access.'
        )
        profile.save()
    elif not has_overdue and profile.is_suspended:
        profile.is_suspended = False
        profile.suspension_reason = ''
        profile.save()

    return has_overdue


def can_borrow(user, book):
    """Returns (allowed: bool, reason: str | None)."""
    check_overdue_and_suspend(user)
    user.profile.refresh_from_db()

    if user.profile.is_suspended:
        return False, (
            'Your account is suspended due to an overdue book. '
            'Return the overdue book or request a 7-day extension to restore borrowing.'
        )

    active_count = BorrowRecord.objects.filter(user=user, status__in=_ACTIVE).count()
    if active_count >= MAX_BORROWS:
        return False, f'You have reached the {MAX_BORROWS}-book limit. Return a book before borrowing another.'

    if book.available_copies <= 0:
        return False, 'This book is currently out of stock. Check back soon.'

    already = BorrowRecord.objects.filter(user=user, book=book, status__in=_ACTIVE).exists()
    if already:
        return False, 'You already have this book on loan.'

    return True, None


def borrow_book(user, book):
    """Issue a new BorrowRecord and decrement inventory. Raises ValueError on failure."""
    ok, error = can_borrow(user, book)
    if not ok:
        raise ValueError(error)

    today = timezone.now().date()
    record = BorrowRecord.objects.create(
        user=user,
        book=book,
        borrow_date=today,
        due_date=today + timedelta(days=BORROW_DAYS),
        status=BorrowRecord.Status.ACTIVE,
    )
    book.available_copies -= 1
    book.save(update_fields=['available_copies', 'updated_at'])
    return record


def return_book(record):
    """Mark record as returned, restore inventory, and re-evaluate suspension. Raises ValueError on failure."""
    if record.status == BorrowRecord.Status.RETURNED:
        raise ValueError('This book has already been returned.')

    record.return_date = timezone.now().date()
    record.status = BorrowRecord.Status.RETURNED
    record.save()

    record.book.available_copies += 1
    record.book.save(update_fields=['available_copies', 'updated_at'])

    check_overdue_and_suspend(record.user)
    return record


def extend_borrow(record):
    """Grant a one-time 7-day extension. Raises ValueError on failure."""
    if record.extended:
        raise ValueError('This borrow has already been extended. No further extensions are allowed.')
    if record.status == BorrowRecord.Status.RETURNED:
        raise ValueError('Cannot extend a returned record.')

    record.extended = True
    record.extended_due_date = record.due_date + timedelta(days=EXTENSION_DAYS)
    record.status = BorrowRecord.Status.EXTENDED
    record.save()

    check_overdue_and_suspend(record.user)
    return record
