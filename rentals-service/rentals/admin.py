from django.contrib import admin

from config.urls import admin_site
from .models import BorrowRecord, BookCache, UserCache


@admin.register(BorrowRecord, site=admin_site)
class BorrowRecordAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user_id', 'book_id', 'status', 'borrow_date', 'due_date',
        'extended', 'return_date',
    ]
    list_filter = ['status', 'extended']
    search_fields = ['user_id', 'book_id']
    ordering = ['-created_at']


@admin.register(BookCache, site=admin_site)
class BookCacheAdmin(admin.ModelAdmin):
    list_display = ['book_id', 'title', 'author', 'available_copies', 'total_copies', 'updated_at']
    search_fields = ['title', 'author']
    ordering = ['book_id']


@admin.register(UserCache, site=admin_site)
class UserCacheAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'username', 'is_suspended', 'updated_at']
    list_filter = ['is_suspended']
    search_fields = ['username']
    ordering = ['user_id']
