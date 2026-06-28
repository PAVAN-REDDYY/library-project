from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'rentals'

router = DefaultRouter()
router.register(r'records', views.BorrowRecordViewSet, basename='record-api')

urlpatterns = [
    path('', views.home, name='home'),
    path('my-borrows/', views.my_borrows, name='my_borrows'),
    path('borrow/<int:book_id>/', views.borrow_book_view, name='borrow'),
    path('return/<int:record_id>/', views.return_book_view, name='return'),
    path('extend/<int:record_id>/', views.extend_borrow_view, name='extend'),
    path('api/', include(router.urls)),
]
