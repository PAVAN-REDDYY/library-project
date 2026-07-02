from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import BorrowRecord, BookCache, UserCache
from . import tasks


class BorrowRecordModelTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

    def test_effective_due_date_uses_extended_date_when_extended(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            extended=True, extended_due_date=self.today + timedelta(days=21),
            status=BorrowRecord.Status.EXTENDED,
        )
        self.assertEqual(record.effective_due_date, self.today + timedelta(days=21))

    def test_effective_due_date_falls_back_to_due_date(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.ACTIVE,
        )
        self.assertEqual(record.effective_due_date, self.today + timedelta(days=14))

    def test_days_remaining_is_none_when_returned(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.RETURNED,
        )
        self.assertIsNone(record.days_remaining)

    def test_can_extend_true_only_for_active_or_overdue_and_not_already_extended(self):
        active = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.ACTIVE,
        )
        self.assertTrue(active.can_extend)

        pending = BorrowRecord.objects.create(
            user_id=1, book_id=2, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.PENDING,
        )
        self.assertFalse(pending.can_extend)

        already_extended = BorrowRecord.objects.create(
            user_id=1, book_id=3, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            extended=True, status=BorrowRecord.Status.EXTENDED,
        )
        self.assertFalse(already_extended.can_extend)

    def test_unique_constraint_blocks_second_active_loan_of_same_book(self):
        # active_loan_key is what actually carries the uniqueness guarantee -
        # a plain unique field, not a conditional/partial UniqueConstraint,
        # since MySQL doesn't support partial unique indexes at all (Django
        # silently skips creating one there - confirmed via its own migration
        # warning - which would make a condition=Q(...) constraint a no-op on
        # MySQL specifically). services.borrow_book() is what actually sets
        # this key; these two creates mirror that by hand.
        BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.ACTIVE, active_loan_key='1:1',
        )
        with self.assertRaises(IntegrityError):
            BorrowRecord.objects.create(
                user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
                status=BorrowRecord.Status.PENDING, active_loan_key='1:1',
            )

    def test_unique_constraint_allows_new_loan_after_return(self):
        BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.RETURNED, active_loan_key=None,
        )
        # return_book() clears active_loan_key back to NULL, and NULL never
        # collides with another NULL (or another value) in a unique index on
        # MySQL/SQLite/Postgres alike, so a fresh loan of the same book by the
        # same user must be allowed.
        second = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.PENDING, active_loan_key='1:1',
        )
        self.assertIsNotNone(second.pk)


class ServicesTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        BookCache.objects.create(book_id=1, title='Dune', author='Frank Herbert', available_copies=1, total_copies=1)
        UserCache.objects.create(user_id=1, username='alice', is_suspended=False)

    @patch('rentals.services.tasks.send_reserve_copy')
    def test_borrow_book_creates_pending_record_and_decrements_cache(self, mock_send_reserve):
        record = services.borrow_book(user_id=1, book_id=1)

        self.assertEqual(record.status, BorrowRecord.Status.PENDING)
        self.assertEqual(record.due_date, self.today + timedelta(days=14))

        cache = BookCache.objects.get(book_id=1)
        self.assertEqual(cache.available_copies, 0)

        mock_send_reserve.assert_called_once_with(record.id, 1)

    @patch('rentals.services.tasks.send_reserve_copy')
    def test_borrow_book_rejects_when_out_of_stock(self, mock_send_reserve):
        BookCache.objects.filter(book_id=1).update(available_copies=0)
        with self.assertRaises(ValueError):
            services.borrow_book(user_id=1, book_id=1)
        mock_send_reserve.assert_not_called()

    @patch('rentals.services.tasks.send_apply_suspension')
    @patch('rentals.services.tasks.send_reserve_copy')
    def test_borrow_book_rejects_when_suspended(self, mock_send_reserve, mock_send_suspend):
        # is_suspended is derived from real overdue records (check_overdue_and_
        # suspend re-evaluates and would just un-suspend a manually-poked flag
        # with no overdue record behind it) - so genuinely earn the suspension
        # via an overdue loan of a different book first.
        BorrowRecord.objects.create(
            user_id=1, book_id=99, borrow_date=self.today - timedelta(days=30),
            due_date=self.today - timedelta(days=16), status=BorrowRecord.Status.ACTIVE,
        )
        with self.assertRaises(ValueError):
            services.borrow_book(user_id=1, book_id=1)
        mock_send_reserve.assert_not_called()

    @patch('rentals.services.tasks.send_reserve_copy')
    def test_borrow_book_rejects_duplicate_active_loan(self, mock_send_reserve):
        services.borrow_book(user_id=1, book_id=1)
        BookCache.objects.filter(book_id=1).update(available_copies=1)  # pretend stock is back
        with self.assertRaises(ValueError):
            services.borrow_book(user_id=1, book_id=1)

    @patch('rentals.services.tasks.send_reserve_copy')
    def test_borrow_book_rejects_at_max_borrows_limit(self, mock_send_reserve):
        services.borrow_book(user_id=1, book_id=1)  # uses the BookCache row from setUp
        for i in range(2, 6):
            BookCache.objects.create(book_id=i, title=f'Book {i}', author='X', available_copies=1, total_copies=1)
            services.borrow_book(user_id=1, book_id=i)
        # Now at MAX_BORROWS (5) active/pending records for user 1 (books 1-5).
        BookCache.objects.create(book_id=6, title='Book 6', author='X', available_copies=1, total_copies=1)
        with self.assertRaises(ValueError):
            services.borrow_book(user_id=1, book_id=6)

    @patch('rentals.services.tasks.send_release_copy')
    def test_return_book_marks_returned_and_fires_release(self, mock_send_release):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.ACTIVE,
        )
        services.return_book(record)
        record.refresh_from_db()
        self.assertEqual(record.status, BorrowRecord.Status.RETURNED)
        self.assertEqual(record.return_date, self.today)
        mock_send_release.assert_called_once_with(record.id, 1)

    def test_return_book_twice_raises(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.RETURNED, return_date=self.today,
        )
        with self.assertRaises(ValueError):
            services.return_book(record)

    def test_extend_borrow_sets_extended_due_date(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.ACTIVE,
        )
        services.extend_borrow(record)
        record.refresh_from_db()
        self.assertTrue(record.extended)
        self.assertEqual(record.status, BorrowRecord.Status.EXTENDED)
        self.assertEqual(record.extended_due_date, self.today + timedelta(days=21))

    def test_extend_borrow_twice_raises(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            extended=True, status=BorrowRecord.Status.EXTENDED,
        )
        with self.assertRaises(ValueError):
            services.extend_borrow(record)

    def test_extend_borrow_rejects_pending_record(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today, due_date=self.today + timedelta(days=14),
            status=BorrowRecord.Status.PENDING,
        )
        with self.assertRaises(ValueError):
            services.extend_borrow(record)

    @patch('rentals.services.tasks.send_apply_suspension')
    def test_check_overdue_and_suspend_flips_status_and_suspends(self, mock_send_suspend):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=self.today - timedelta(days=20),
            due_date=self.today - timedelta(days=6), status=BorrowRecord.Status.ACTIVE,
        )
        has_overdue = services.check_overdue_and_suspend(user_id=1)

        self.assertTrue(has_overdue)
        record.refresh_from_db()
        self.assertEqual(record.status, BorrowRecord.Status.OVERDUE)

        cache = UserCache.objects.get(user_id=1)
        self.assertTrue(cache.is_suspended)
        mock_send_suspend.assert_called_once()
        args = mock_send_suspend.call_args.args
        self.assertEqual(args[0], 1)
        self.assertTrue(args[1])

    @patch('rentals.services.tasks.send_apply_suspension')
    def test_check_overdue_and_suspend_unsuspends_once_clear(self, mock_send_suspend):
        UserCache.objects.filter(user_id=1).update(is_suspended=True)
        services.check_overdue_and_suspend(user_id=1)

        cache = UserCache.objects.get(user_id=1)
        self.assertFalse(cache.is_suspended)
        mock_send_suspend.assert_called_once_with(1, False, '')


class TaskConsumerTests(TestCase):
    """Task functions are just plain Python functions under the @app.task
    decorator - calling them directly needs no broker at all."""

    def test_upsert_book_cache_creates_and_updates(self):
        tasks.upsert_book_cache(book_id=1, title='Dune', author='Frank Herbert', available_copies=2, total_copies=3)
        cache = BookCache.objects.get(book_id=1)
        self.assertEqual(cache.title, 'Dune')
        self.assertEqual(cache.available_copies, 2)

        tasks.upsert_book_cache(book_id=1, title='Dune', author='Frank Herbert', available_copies=1, total_copies=3)
        cache.refresh_from_db()
        self.assertEqual(cache.available_copies, 1)

    def test_upsert_user_cache_creates_and_updates(self):
        tasks.upsert_user_cache(user_id=1, username='alice', is_suspended=False)
        cache = UserCache.objects.get(user_id=1)
        self.assertFalse(cache.is_suspended)

        tasks.upsert_user_cache(user_id=1, username='alice', is_suspended=True)
        cache.refresh_from_db()
        self.assertTrue(cache.is_suspended)

    def test_confirm_borrow_flips_pending_to_active(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.PENDING,
        )
        tasks.confirm_borrow(record.id)
        record.refresh_from_db()
        self.assertEqual(record.status, BorrowRecord.Status.ACTIVE)

    def test_confirm_borrow_is_idempotent_on_redelivery(self):
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.PENDING,
        )
        tasks.confirm_borrow(record.id)
        tasks.confirm_borrow(record.id)  # redelivery - must not error or change anything
        record.refresh_from_db()
        self.assertEqual(record.status, BorrowRecord.Status.ACTIVE)

    def test_reject_borrow_flips_status_and_restores_cache(self):
        BookCache.objects.create(book_id=1, title='Dune', author='Frank Herbert', available_copies=0, total_copies=1)
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.PENDING,
        )
        tasks.reject_borrow(record.id, 'This book is currently out of stock.', 1)

        record.refresh_from_db()
        self.assertEqual(record.status, BorrowRecord.Status.REJECTED)
        self.assertEqual(record.reject_reason, 'This book is currently out of stock.')

        cache = BookCache.objects.get(book_id=1)
        self.assertEqual(cache.available_copies, 1)

    def test_reject_borrow_is_idempotent_on_redelivery(self):
        BookCache.objects.create(book_id=1, title='Dune', author='Frank Herbert', available_copies=0, total_copies=1)
        record = BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.PENDING,
        )
        tasks.reject_borrow(record.id, 'out of stock', 1)
        tasks.reject_borrow(record.id, 'out of stock', 1)  # redelivery

        cache = BookCache.objects.get(book_id=1)
        # Restored exactly once, not twice, despite two deliveries.
        self.assertEqual(cache.available_copies, 1)


class ViewTests(TestCase):
    def _login_as(self, user_id, username, is_staff):
        from types import SimpleNamespace
        from common.jwt_auth import encode_token, COOKIE_NAME
        token = encode_token(SimpleNamespace(id=user_id, username=username, is_staff=is_staff))
        self.client.cookies[COOKIE_NAME] = token

    def test_home_page_loads(self):
        response = self.client.get(reverse('rentals:home'))
        self.assertEqual(response.status_code, 200)

    def test_available_now_counts_remaining_copies_not_titles_with_stock(self):
        # A title keeps counting as "has stock" until it fully depletes, so a
        # naive count of titles with available_copies > 0 doesn't move when a
        # multi-copy title is borrowed from - only the sum of remaining
        # copies does, which is the number this page should show.
        BookCache.objects.create(book_id=1, title='A', author='X', available_copies=4, total_copies=5)
        BookCache.objects.create(book_id=2, title='B', author='Y', available_copies=1, total_copies=1)
        response = self.client.get(reverse('rentals:home'))
        self.assertEqual(response.context['available_books'], 5)

    def test_recent_activity_hidden_from_anonymous_visitors(self):
        BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.ACTIVE,
            active_loan_key='1:1',
        )
        UserCache.objects.create(user_id=1, username='alice', is_suspended=False)
        response = self.client.get(reverse('rentals:home'))
        self.assertNotContains(response, 'alice')
        self.assertNotContains(response, 'Recent Activity')

    def test_recent_activity_hidden_from_other_logged_in_patrons(self):
        # This is the actual bug reported: a second, unrelated logged-in user
        # must not see the first user's borrowing activity/identity.
        BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.ACTIVE,
            active_loan_key='1:1',
        )
        UserCache.objects.create(user_id=1, username='alice', is_suspended=False)
        self._login_as(user_id=2, username='bob', is_staff=False)
        response = self.client.get(reverse('rentals:home'))
        self.assertNotContains(response, 'alice')
        self.assertNotContains(response, 'Recent Activity')

    def test_recent_activity_visible_to_staff(self):
        BorrowRecord.objects.create(
            user_id=1, book_id=1, borrow_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14), status=BorrowRecord.Status.ACTIVE,
            active_loan_key='1:1',
        )
        UserCache.objects.create(user_id=1, username='alice', is_suspended=False)
        self._login_as(user_id=99, username='admin', is_staff=True)
        response = self.client.get(reverse('rentals:home'))
        self.assertContains(response, 'alice')
        self.assertContains(response, 'Recent Activity')
