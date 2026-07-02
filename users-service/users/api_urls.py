from django.urls import path
from .views_api import UserListAPIView

urlpatterns = [
    path('', UserListAPIView.as_view(), name='user-list-api'),
]
