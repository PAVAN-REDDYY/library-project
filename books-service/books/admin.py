from django.contrib import admin

from config.urls import admin_site

from .models import Book, ReservationLog


class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'genre', 'total_copies', 'available_copies', 'is_available', 'added_at']
    list_filter = ['genre']
    search_fields = ['title', 'author', 'isbn']
    list_editable = ['total_copies', 'available_copies']
    readonly_fields = ['added_at', 'updated_at']
    fieldsets = [
        (None, {'fields': ['title', 'author', 'isbn', 'genre', 'description']}),
        ('Inventory', {'fields': ['total_copies', 'available_copies']}),
        ('Timestamps', {'fields': ['added_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def is_available(self, obj):
        return obj.is_available
    is_available.boolean = True
    is_available.short_description = 'In Stock'


class ReservationLogAdmin(admin.ModelAdmin):
    list_display = ['record_id', 'event_type', 'outcome', 'book_id', 'created_at']
    list_filter = ['event_type', 'outcome']
    search_fields = ['record_id', 'book_id']
    readonly_fields = ['record_id', 'event_type', 'outcome', 'book_id', 'created_at']


admin_site.register(Book, BookAdmin)
admin_site.register(ReservationLog, ReservationLogAdmin)
