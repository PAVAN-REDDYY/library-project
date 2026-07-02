from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('users.urls')),
    # Read-only, service-to-service: rentals-service's bootstrap_caches
    # management command GETs this once at startup to hydrate its UserCache.
    path('api/users/', include('users.api_urls')),
]
