from django.contrib import admin
from .models import Book


@admin.register(Book)
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
