from django.db import models

BORROW_DAYS = 14
EXTENSION_DAYS = 7
MAX_BORROWS = 5


class BorrowRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        EXTENDED = 'extended', 'Extended'
        RETURNED = 'returned', 'Returned'
        OVERDUE = 'overdue', 'Overdue'
        REJECTED = 'rejected', 'Rejected'

    # Plain integer fields, not ForeignKeys - User and Book live in different
    # services' databases now, so there's no way to have a real FK to them.
    user_id = models.PositiveIntegerField()
    book_id = models.PositiveIntegerField()
    borrow_date = models.DateField()
    due_date = models.DateField()
    extended = models.BooleanField(default=False)
    extended_due_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.CharField(max_length=255, blank=True)
    # Set to f'{user_id}:{book_id}' while the loan is pending/active/extended/
    # overdue, and back to NULL once returned/rejected. This (not a
    # conditional/partial UniqueConstraint) is what enforces "one active loan
    # per user+book" at the DB level: MySQL has no support for partial unique
    # indexes at all (a UniqueConstraint(condition=...) is silently NOT
    # created there - confirmed via Django's own migration warning - which
    # would make this guarantee silently vanish on MySQL specifically). A
    # plain unique field works identically on MySQL/SQLite/Postgres because
    # all three treat NULL as distinct from every other NULL in a unique
    # index, which is exactly the "ignore terminal-state rows" behavior a
    # partial index would have given directly.
    active_loan_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Borrow Record'
        verbose_name_plural = 'Borrow Records'

    def __str__(self):
        return f'user#{self.user_id} -> book#{self.book_id} ({self.status})'

    @property
    def effective_due_date(self):
        if self.extended and self.extended_due_date:
            return self.extended_due_date
        return self.due_date

    @property
    def days_remaining(self):
        if self.status == self.Status.RETURNED:
            return None
        from django.utils import timezone
        return (self.effective_due_date - timezone.now().date()).days

    @property
    def can_extend(self):
        return (
            not self.extended
            and self.status in [self.Status.ACTIVE, self.Status.OVERDUE]
        )


class BookCache(models.Model):
    """Local read-model mirror of books-service's Book, kept fresh via the
    upsert_book_cache task below (pushed by books-service on every change) plus
    a one-time bootstrap sync on first startup. NOT the source of truth for
    stock - books-service is - this is only used for fast local eligibility
    checks without a network call per request."""
    book_id = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    # Signed, not PositiveIntegerField: during the optimistic-decrement-then-
    # possibly-restore dance (see borrow_book/reject_borrow) a transient
    # negative should be visible/debuggable rather than raising a DB error.
    available_copies = models.IntegerField()
    total_copies = models.PositiveIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} ({self.available_copies}/{self.total_copies})'


class UserCache(models.Model):
    """Local read-model mirror of users-service's UserProfile.is_suspended,
    kept fresh the same way as BookCache."""
    user_id = models.PositiveIntegerField(unique=True)
    username = models.CharField(max_length=150)
    is_suspended = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username or f'user#{self.user_id}'
