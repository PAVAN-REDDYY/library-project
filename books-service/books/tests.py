import datetime
from unittest.mock import patch, ANY

import jwt
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .models import Book, ReservationLog
from .tasks import reserve_copy, release_copy


def _make_jwt(user_id, username, is_staff=False):
    """This service never issues JWTs itself (users-service does) - this
    stands in for that, so tests can simulate an authenticated/staff request
    without a local User model or AUTHENTICATION_BACKENDS to log in against."""
    payload = {
        'user_id': user_id, 'username': username, 'is_staff': is_staff,
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm='HS256')


class BookModelTests(TestCase):
    def test_str(self):
        book = Book.objects.create(title='Dune', author='Frank Herbert', total_copies=3, available_copies=3)
        self.assertEqual(str(book), 'Dune — Frank Herbert')

    def test_is_available_true_when_copies_left(self):
        book = Book.objects.create(title='Dune', author='Frank Herbert', total_copies=3, available_copies=1)
        self.assertTrue(book.is_available)

    def test_is_available_false_when_no_copies_left(self):
        book = Book.objects.create(title='Dune', author='Frank Herbert', total_copies=3, available_copies=0)
        self.assertFalse(book.is_available)

    def test_copies_on_loan(self):
        book = Book.objects.create(title='Dune', author='Frank Herbert', total_copies=5, available_copies=2)
        self.assertEqual(book.copies_on_loan, 3)

    def test_default_ordering_by_title(self):
        Book.objects.create(title='Zebra Tales', author='A')
        Book.objects.create(title='Aardvark Adventures', author='B')
        titles = list(Book.objects.values_list('title', flat=True))
        self.assertEqual(titles, ['Aardvark Adventures', 'Zebra Tales'])


class ReserveCopyTaskTests(TestCase):
    """reserve_copy is invoked directly as a plain function - no broker needed
    to call it. The notification back to rentals-service goes through
    books.tasks.send_task (common.dispatch.send_task, imported by name into
    this module) - patching that name directly, rather than the real
    app.send_task, means these tests don't depend on CELERY_TASK_ALWAYS_EAGER
    at all (which matters because Book.objects.create() in setUp also fires
    the unrelated sync_book_cache signal, which would otherwise try a real
    broker connection outside of each test's own @patch scope).
    """

    def setUp(self):
        self.book = Book.objects.create(
            title='Dune', author='Frank Herbert', total_copies=1, available_copies=1,
        )

    @patch('books.tasks.send_task')
    def test_reserve_confirms_when_stock_available(self, mock_send_task):
        reserve_copy(record_id=1, book_id=self.book.id)

        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 0)

        log = ReservationLog.objects.get(record_id=1, event_type='reserve')
        self.assertEqual(log.outcome, 'confirmed')

        mock_send_task.assert_called_once_with(
            ANY, 'rentals.tasks.confirm_borrow', args=[1], queue='rentals_queue',
        )

    @patch('books.tasks.send_task')
    def test_reserve_rejects_when_out_of_stock(self, mock_send_task):
        # First call claims the only copy.
        reserve_copy(record_id=1, book_id=self.book.id)
        # Second call, different record_id, hits zero stock and must reject
        # without ever going negative.
        reserve_copy(record_id=2, book_id=self.book.id)

        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 0)

        log = ReservationLog.objects.get(record_id=2, event_type='reserve')
        self.assertEqual(log.outcome, 'rejected')

        mock_send_task.assert_called_with(
            ANY,
            'rentals.tasks.reject_borrow',
            args=[2, 'This book is currently out of stock.', self.book.id],
            queue='rentals_queue',
        )

    @patch('books.tasks.send_task')
    def test_reserve_is_idempotent_for_same_record_id(self, mock_send_task):
        # Call reserve_copy twice with the same record_id (simulating
        # at-least-once redelivery of the same message) - stock must only be
        # decremented once.
        reserve_copy(record_id=1, book_id=self.book.id)
        reserve_copy(record_id=1, book_id=self.book.id)

        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 0)
        self.assertEqual(
            ReservationLog.objects.filter(record_id=1, event_type='reserve').count(), 1,
        )
        # Both deliveries still notify rentals-service with the same outcome
        # (fire-and-forget re-send is fine/expected), just no double-decrement.
        self.assertEqual(mock_send_task.call_count, 2)
        for call in mock_send_task.call_args_list:
            self.assertEqual(call.args[1], 'rentals.tasks.confirm_borrow')

    @patch('books.tasks.send_task')
    def test_reserve_never_goes_negative(self, mock_send_task):
        book = Book.objects.create(title='Foundation', author='Asimov', total_copies=1, available_copies=0)

        reserve_copy(record_id=10, book_id=book.id)

        book.refresh_from_db()
        self.assertEqual(book.available_copies, 0)
        log = ReservationLog.objects.get(record_id=10, event_type='reserve')
        self.assertEqual(log.outcome, 'rejected')


class ReleaseCopyTaskTests(TestCase):
    def setUp(self):
        self.book = Book.objects.create(
            title='Dune', author='Frank Herbert', total_copies=2, available_copies=0,
        )

    def test_release_increments_available_copies(self):
        release_copy(record_id=5, book_id=self.book.id)

        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)
        self.assertTrue(
            ReservationLog.objects.filter(record_id=5, event_type='release', outcome='confirmed').exists()
        )

    def test_release_is_idempotent_for_same_record_id(self):
        release_copy(record_id=5, book_id=self.book.id)
        release_copy(record_id=5, book_id=self.book.id)

        self.book.refresh_from_db()
        # Only incremented once despite two deliveries for the same record_id.
        self.assertEqual(self.book.available_copies, 1)
        self.assertEqual(
            ReservationLog.objects.filter(record_id=5, event_type='release').count(), 1,
        )


class BookCacheSyncSignalTests(TestCase):
    """post_save on Book should push the current state to rentals-service's
    cache via Celery - patches books.signals.send_task (the common.dispatch
    wrapper name imported into that module) directly, same reasoning as
    ReserveCopyTaskTests above."""

    @patch('books.signals.send_task')
    def test_saving_a_book_sends_upsert_book_cache_task(self, mock_send_task):
        book = Book.objects.create(
            title='Dune', author='Frank Herbert', total_copies=3, available_copies=3,
        )

        mock_send_task.assert_called_with(
            ANY,
            'rentals.tasks.upsert_book_cache',
            args=[book.id, 'Dune', 'Frank Herbert', 3, 3],
            queue='rentals_queue',
        )


class BookViewTests(TestCase):
    def setUp(self):
        self.book = Book.objects.create(
            title='Dune', author='Frank Herbert', genre='Sci-Fi',
            total_copies=3, available_copies=2,
        )

    def test_book_list_status_ok_and_contains_book(self):
        response = self.client.get(reverse('books:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dune')

    def test_book_list_search_by_query(self):
        Book.objects.create(title='Foundation', author='Isaac Asimov', total_copies=1, available_copies=1)
        response = self.client.get(reverse('books:list'), {'q': 'Dune'})
        self.assertContains(response, 'Dune')
        self.assertNotContains(response, 'Foundation')

    def test_book_list_filter_by_genre(self):
        Book.objects.create(
            title='Foundation', author='Isaac Asimov', genre='Classic',
            total_copies=1, available_copies=1,
        )
        response = self.client.get(reverse('books:list'), {'genre': 'Sci-Fi'})
        self.assertContains(response, 'Dune')
        self.assertNotContains(response, 'Foundation')

    def test_book_detail_status_ok(self):
        response = self.client.get(reverse('books:detail', args=[self.book.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dune')
        self.assertContains(response, 'Frank Herbert')

    def test_book_detail_404_for_missing_book(self):
        response = self.client.get(reverse('books:detail', args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_book_detail_anonymous_shows_login_prompt(self):
        response = self.client.get(reverse('books:detail', args=[self.book.pk]))
        self.assertContains(response, 'Login to Borrow')

    def test_book_detail_out_of_stock_has_no_borrow_link(self):
        # The out-of-stock messaging only shows once past the "please log in"
        # branch (matches the original app's behavior: an anonymous visitor
        # always sees the login prompt first, regardless of stock), so this
        # needs a real authenticated request - there's no local User model or
        # AUTHENTICATION_BACKENDS here for client.login()/force_login() to
        # work against, so simulate the JWT cookie users-service would issue.
        out_of_stock = Book.objects.create(
            title='Rare Book', author='Someone', total_copies=1, available_copies=0,
        )
        self.client.cookies['access_token'] = _make_jwt(user_id=1, username='alice')
        response = self.client.get(reverse('books:detail', args=[out_of_stock.pk]))
        self.assertContains(response, 'Out of Stock')
        self.assertNotContains(response, 'Borrow this book')


class BookApiTests(TestCase):
    def setUp(self):
        self.book = Book.objects.create(
            title='Dune', author='Frank Herbert', total_copies=3, available_copies=2,
        )

    def test_list_is_public(self):
        response = self.client.get('/books/api/')
        self.assertEqual(response.status_code, 200)

    def test_retrieve_is_public(self):
        response = self.client.get(f'/books/api/{self.book.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Dune')

    def test_create_requires_admin(self):
        response = self.client.post('/books/api/', {
            'title': 'New Book', 'author': 'Someone', 'total_copies': 1, 'available_copies': 1,
        })
        self.assertIn(response.status_code, (401, 403))
