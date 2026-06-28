from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import BookRental


class BookRentalTests(TestCase):
    def setUp(self):
        self.rental = BookRental.objects.create(
            book_title='Django for Beginners',
            author_name='William S. Vincent',
            borrower_name='Carol',
            borrower_email='carol@example.com',
            rental_date=date(2026, 3, 1),
            return_date=date(2026, 3, 15),
        )

    def test_str(self):
        self.assertIn('Django for Beginners', str(self.rental))

    def test_defaults(self):
        self.assertEqual(self.rental.status, BookRental.Status.BORROWED)
        self.assertEqual(self.rental.fine_amount, Decimal('0.00'))

    def test_list_page(self):
        response = self.client.get(reverse('rentals:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Carol')

    def test_api_list(self):
        response = self.client.get('/api/book-rentals/')
        self.assertEqual(response.status_code, 200)
