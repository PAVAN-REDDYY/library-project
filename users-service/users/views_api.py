from rest_framework import generics, permissions
from django.contrib.auth.models import User
from .serializers import UserSerializer


class UserListAPIView(generics.ListAPIView):
    """Read-only, service-to-service: rentals-service's bootstrap_caches
    management command GETs this once at startup to hydrate its UserCache.
    Ongoing sync after that is the async users.tasks/rentals.tasks flow."""
    queryset = User.objects.select_related('profile').all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None  # rentals-service's bootstrap sync wants the full list in one call
