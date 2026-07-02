"""
Custom AdminSite for services with no local User table (books-service,
rentals-service). Django's default admin login calls authenticate() against
a local user model, which doesn't exist in these services - staff identity
comes entirely from the JWT cookie (common.jwt_auth), issued by logging in
through users-service. So: permission check reads request.user.is_staff (set
by JWTAuthenticationMiddleware), and the login view is just a redirect to
users-service's login page rather than a local login form.

users-service keeps the plain django.contrib.admin.site - it has a real User
table and real session auth, so the stock admin login works there unmodified.
"""
from django.contrib import admin
from django.shortcuts import redirect


class JWTTrustingAdminSite(admin.AdminSite):
    def has_permission(self, request):
        return bool(
            getattr(request.user, 'is_authenticated', False)
            and getattr(request.user, 'is_staff', False)
        )

    def login(self, request, extra_context=None):
        return redirect(f'/accounts/login/?next={request.path}')
