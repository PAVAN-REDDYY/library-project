"""Small helper so a missing required secret fails loudly and clearly at
startup, instead of silently falling back to a hardcoded value that would
otherwise need to live in committed source (and, in JWT_SECRET's case, a
mismatched fallback between services would break cross-service auth in a
confusing way rather than failing fast)."""
import os

from django.core.exceptions import ImproperlyConfigured


def require_env(name, hint=''):
    value = os.environ.get(name)
    if not value:
        message = (
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example (repo root) to .env and fill it in."
        )
        if hint:
            message += f' {hint}'
        raise ImproperlyConfigured(message)
    return value
