from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

BORROW_DAYS = 14
EXTENSION_DAYS = 7
MAX_BORROWS = 5


class BorrowRecord(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXTENDED = 'extended', 'Extended'
        RETURNED = 'returned', 'Returned'
        OVERDUE = 'overdue', 'Overdue'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='borrow_records')
    book = models.ForeignKey('books.Book', on_delete=models.CASCADE, related_name='borrow_records')
    borrow_date = models.DateField()
    due_date = models.DateField()
    extended = models.BooleanField(default=False)
    extended_due_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Borrow Record'
        verbose_name_plural = 'Borrow Records'

    def __str__(self):
        return f'{self.user.username} → {self.book.title} ({self.status})'

    @property
    def effective_due_date(self):
        if self.extended and self.extended_due_date:
            return self.extended_due_date
        return self.due_date

    @property
    def days_remaining(self):
        if self.status == self.Status.RETURNED:
            return None
        return (self.effective_due_date - timezone.now().date()).days

    @property
    def can_extend(self):
        return (
            not self.extended
            and self.status in [self.Status.ACTIVE, self.Status.OVERDUE]
        )
