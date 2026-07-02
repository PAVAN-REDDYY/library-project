from rest_framework import serializers
from .models import BorrowRecord, BookCache, UserCache


class BookCacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookCache
        fields = ['book_id', 'title', 'author', 'available_copies', 'total_copies']


class UserCacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCache
        fields = ['user_id', 'username', 'is_suspended']


class BorrowRecordSerializer(serializers.ModelSerializer):
    book_detail = serializers.SerializerMethodField()
    borrower = serializers.SerializerMethodField()
    effective_due_date = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()
    can_extend = serializers.ReadOnlyField()

    class Meta:
        model = BorrowRecord
        fields = [
            'id', 'borrower', 'book_detail',
            'borrow_date', 'due_date', 'extended', 'extended_due_date',
            'effective_due_date', 'return_date', 'status', 'reject_reason',
            'days_remaining', 'can_extend', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'borrow_date', 'due_date', 'extended', 'extended_due_date',
            'return_date', 'status', 'reject_reason', 'created_at', 'updated_at',
        ]

    def get_book_detail(self, obj):
        cache = BookCache.objects.filter(book_id=obj.book_id).first()
        return BookCacheSerializer(cache).data if cache else {'book_id': obj.book_id}

    def get_borrower(self, obj):
        cache = UserCache.objects.filter(user_id=obj.user_id).first()
        return UserCacheSerializer(cache).data if cache else {'user_id': obj.user_id}
