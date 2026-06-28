from django.contrib import admin
from django.utils.html import format_html
from .models import BorrowRecord


@admin.register(BorrowRecord)
class BorrowRecordAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'book', 'borrow_date', 'due_date', 'extended',
        'extended_due_date', 'return_date', 'status_badge',
    ]
    list_filter = ['status', 'extended']
    search_fields = ['user__username', 'user__email', 'book__title', 'book__author']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'borrow_date'
    raw_id_fields = ['user', 'book']

    def status_badge(self, obj):
        colors = {
            'active': '#2d6a4f',
            'extended': '#1d3557',
            'returned': '#555',
            'overdue': '#c1121f',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = 'Status'
