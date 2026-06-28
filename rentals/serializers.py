from rest_framework import serializers
from .models import BorrowRecord
from books.serializers import BookSerializer
from users.serializers import UserSerializer


class BorrowRecordSerializer(serializers.ModelSerializer):
    book_detail = BookSerializer(source='book', read_only=True)
    borrower = UserSerializer(source='user', read_only=True)
    effective_due_date = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()
    can_extend = serializers.ReadOnlyField()

    class Meta:
        model = BorrowRecord
        fields = [
            'id', 'borrower', 'book_detail',
            'borrow_date', 'due_date', 'extended', 'extended_due_date',
            'effective_due_date', 'return_date', 'status',
            'days_remaining', 'can_extend',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'borrow_date', 'due_date', 'extended', 'extended_due_date',
            'return_date', 'status', 'created_at', 'updated_at',
        ]
