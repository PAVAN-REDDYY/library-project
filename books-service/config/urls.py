from django.urls import path, include

from common.admin_site import JWTTrustingAdminSite

admin_site = JWTTrustingAdminSite(name='admin')

urlpatterns = [
    path('admin/', admin_site.urls),
    path('books/', include('books.urls')),
]
