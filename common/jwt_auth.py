"""
Shared JWT contract used by all three services.

users-service is the only issuer (see its users/auth_utils.py). books-service and
rentals-service only ever verify: they hold no session/password state of their own,
so a request's identity is whatever this module can decode from the token.

Token carries: user_id, username, is_staff, exp, iat. Signed HS256 with JWT_SECRET,
which must be identical across all three services' settings (env-overridable, same
default-dev-value convention the original project used for SECRET_KEY).
"""
import datetime

import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

COOKIE_NAME = 'access_token'
ALGORITHM = 'HS256'


class RemoteUser:
    """Stand-in for auth.User in services that don't have a local Users table."""

    def __init__(self, payload):
        self.id = payload['user_id']
        self.pk = self.id
        self.username = payload.get('username', '')
        self.is_staff = bool(payload.get('is_staff', False))
        self.is_active = True
        self.is_authenticated = True
        self.is_anonymous = False

    def __str__(self):
        return self.username


def encode_token(user):
    """Used only by users-service at login/registration time."""
    now = datetime.datetime.utcnow()
    payload = {
        'user_id': user.id,
        'username': user.username,
        'is_staff': user.is_staff,
        'iat': now,
        'exp': now + datetime.timedelta(hours=12),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def _extract_raw_token(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1]
    return request.COOKIES.get(COOKIE_NAME)


def decode_request(request):
    """Returns a RemoteUser or None. Raises AuthenticationFailed on a malformed/expired token
    (but a *missing* token just returns None, so anonymous access to public endpoints still works)."""
    token = _extract_raw_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        raise AuthenticationFailed('Invalid or expired token')
    return RemoteUser(payload)


class JWTCookieAuthentication(BaseAuthentication):
    """DRF authentication class for books-service/rentals-service API views."""

    def authenticate(self, request):
        user = decode_request(request)
        if user is None:
            return None
        return (user, None)


class JWTAuthenticationMiddleware:
    """Populates request.user for server-rendered template views in books-service/
    rentals-service, so @login_required and {{ request.user.username }} keep working
    without a local Django auth backend. users-service does NOT use this middleware -
    it keeps real Django session auth and only adds JWT issuance on top."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            user = decode_request(request)
        except AuthenticationFailed:
            user = None
        request.user = user if user is not None else AnonymousUser()
        return self.get_response(request)
