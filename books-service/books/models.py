from django.db import models


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    isbn = models.CharField(max_length=20, unique=True, blank=True, null=True)
    genre = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        verbose_name = 'Book'
        verbose_name_plural = 'Books'

    def __str__(self):
        return f'{self.title} — {self.author}'

    @property
    def is_available(self):
        return self.available_copies > 0

    @property
    def copies_on_loan(self):
        return self.total_copies - self.available_copies


class ReservationLog(models.Model):
    """Idempotency guard for reserve_copy/release_copy tasks - a redelivered
    task for a record_id we've already handled must not touch available_copies
    a second time."""
    record_id = models.PositiveIntegerField()
    event_type = models.CharField(max_length=10, choices=[('reserve', 'reserve'), ('release', 'release')])
    outcome = models.CharField(max_length=10, blank=True)  # 'confirmed'/'rejected', only meaningful for 'reserve'
    book_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['record_id', 'event_type'], name='uniq_record_event')
        ]

    def __str__(self):
        return f'{self.event_type}#{self.record_id} -> {self.outcome or "pending"}'
