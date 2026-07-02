from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from common.jwt_auth import COOKIE_NAME
from .models import UserProfile
from .tasks import apply_suspension


class UserProfileSignalTests(TestCase):
    def test_profile_auto_created_on_user_creation(self):
        user = User.objects.create_user(username='alice', password='pw12345')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertFalse(user.profile.is_suspended)

    def test_no_duplicate_profile_on_user_resave(self):
        user = User.objects.create_user(username='bob', password='pw12345')
        user.email = 'bob@example.com'
        user.save()
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)


class ApplySuspensionTaskTests(TestCase):
    def test_apply_suspension_updates_existing_profile(self):
        user = User.objects.create_user(username='carol', password='pw12345')
        self.assertFalse(user.profile.is_suspended)

        apply_suspension(user.id, True, 'Overdue book: The Hobbit')

        user.profile.refresh_from_db()
        self.assertTrue(user.profile.is_suspended)
        self.assertEqual(user.profile.suspension_reason, 'Overdue book: The Hobbit')

    def test_apply_suspension_can_unsuspend(self):
        user = User.objects.create_user(username='dave', password='pw12345')
        apply_suspension(user.id, True, 'Overdue')
        apply_suspension(user.id, False, '')

        user.profile.refresh_from_db()
        self.assertFalse(user.profile.is_suspended)
        self.assertEqual(user.profile.suspension_reason, '')

    def test_apply_suspension_missing_profile_is_noop(self):
        # Should not raise even though no matching UserProfile exists.
        apply_suspension(99999, True, 'irrelevant')

    def test_apply_suspension_is_idempotent(self):
        user = User.objects.create_user(username='erin', password='pw12345')
        apply_suspension(user.id, True, 'Overdue book')
        apply_suspension(user.id, True, 'Overdue book')

        user.profile.refresh_from_db()
        self.assertTrue(user.profile.is_suspended)
        self.assertEqual(user.profile.suspension_reason, 'Overdue book')


class RegisterViewTests(TestCase):
    def test_register_redirects_and_sets_jwt_cookie(self):
        response = self.client.post(reverse('users:register'), {
            'first_name': 'Grace',
            'last_name': 'Hopper',
            'email': 'grace@example.com',
            'username': 'grace',
            'password1': 'SuperSecret123!',
            'password2': 'SuperSecret123!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('http://localhost:8003'))
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertNotEqual(response.cookies[COOKIE_NAME].value, '')
        self.assertTrue(response.cookies[COOKIE_NAME]['httponly'])
        self.assertEqual(response.cookies[COOKIE_NAME]['samesite'], 'Lax')

        self.assertTrue(User.objects.filter(username='grace').exists())
        self.assertTrue(UserProfile.objects.filter(user__username='grace').exists())

    def test_register_creates_profile_via_signal(self):
        self.client.post(reverse('users:register'), {
            'first_name': 'Ada',
            'last_name': 'Lovelace',
            'email': 'ada@example.com',
            'username': 'ada',
            'password1': 'SuperSecret123!',
            'password2': 'SuperSecret123!',
        })
        user = User.objects.get(username='ada')
        self.assertTrue(hasattr(user, 'profile'))


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='frank', password='pw12345')

    def test_login_redirects_to_rentals_home_and_sets_jwt_cookie(self):
        response = self.client.post(reverse('users:login'), {
            'username': 'frank',
            'password': 'pw12345',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'http://localhost:8003/')
        self.assertIn(COOKIE_NAME, response.cookies)

    def test_login_redirects_to_explicit_next(self):
        next_url = 'http://localhost:8002/books/42/'
        response = self.client.post(
            f"{reverse('users:login')}?next={next_url}",
            {'username': 'frank', 'password': 'pw12345'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
        self.assertIn(COOKIE_NAME, response.cookies)

    def test_login_invalid_credentials_shows_error(self):
        response = self.client.post(reverse('users:login'), {
            'username': 'frank',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(COOKIE_NAME, response.cookies)


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='gina', password='pw12345')

    def test_logout_accepts_get_and_clears_cookie(self):
        self.client.login(username='gina', password='pw12345')
        response = self.client.get(reverse('users:logout'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'http://localhost:8003/')
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[COOKIE_NAME].value, '')

    def test_logout_accepts_post(self):
        self.client.login(username='gina', password='pw12345')
        response = self.client.post(reverse('users:logout'))
        self.assertEqual(response.status_code, 302)


class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='harold', password='pw12345')

    def test_profile_requires_login(self):
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_profile_renders_for_logged_in_user(self):
        self.client.login(username='harold', password='pw12345')
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['profile'], self.user.profile)
        self.assertContains(response, 'View My Borrows')


class UserListAPITests(TestCase):
    def test_user_list_api_returns_flat_and_nested_is_suspended(self):
        user = User.objects.create_user(username='ivy', password='pw12345')
        user.profile.is_suspended = True
        user.profile.suspension_reason = 'Overdue'
        user.profile.save()

        response = self.client.get(reverse('user-list-api'))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # pagination_class = None, so this is a plain list, not a paginated envelope.
        self.assertIsInstance(data, list)
        row = next(r for r in data if r['username'] == 'ivy')
        self.assertTrue(row['is_suspended'])
        self.assertTrue(row['profile']['is_suspended'])
