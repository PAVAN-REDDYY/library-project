from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'books'

router = DefaultRouter()
router.register(r'', views.BookViewSet, basename='book-api')

urlpatterns = [
    path('', views.book_list, name='list'),
    path('<int:pk>/', views.book_detail, name='detail'),
    path('api/', include(router.urls)),
]
