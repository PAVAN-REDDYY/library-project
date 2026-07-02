import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from rentals.models import BookCache, UserCache


class Command(BaseCommand):
    help = 'One-time sync: hydrate BookCache/UserCache from books-service and users-service over HTTP.'

    def handle(self, *args, **options):
        books_resp = requests.get(f'{settings.BOOKS_SERVICE_URL}/books/api/', timeout=10)
        books_resp.raise_for_status()
        payload = books_resp.json()
        books = payload.get('results', payload) if isinstance(payload, dict) else payload
        for b in books:
            BookCache.objects.update_or_create(
                book_id=b['id'],
                defaults={
                    'title': b['title'], 'author': b['author'],
                    'available_copies': b['available_copies'], 'total_copies': b['total_copies'],
                },
            )
        self.stdout.write(self.style.SUCCESS(f'Synced {len(books)} books.'))

        users_resp = requests.get(f'{settings.USERS_SERVICE_URL}/api/users/', timeout=10)
        users_resp.raise_for_status()
        payload = users_resp.json()
        users = payload.get('results', payload) if isinstance(payload, dict) else payload
        for u in users:
            UserCache.objects.update_or_create(
                user_id=u['id'],
                defaults={'username': u['username'], 'is_suspended': u.get('is_suspended', False)},
            )
        self.stdout.write(self.style.SUCCESS(f'Synced {len(users)} users.'))
