from rest_framework import serializers
from .models import Book


class BookSerializer(serializers.ModelSerializer):
    is_available = serializers.ReadOnlyField()
    copies_on_loan = serializers.ReadOnlyField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'isbn', 'genre', 'description',
            'total_copies', 'available_copies', 'copies_on_loan',
            'is_available', 'added_at', 'updated_at',
        ]
        read_only_fields = ['added_at', 'updated_at']

    def validate(self, attrs):
        total = attrs.get('total_copies', getattr(self.instance, 'total_copies', 1))
        available = attrs.get('available_copies', getattr(self.instance, 'available_copies', 1))
        if available > total:
            raise serializers.ValidationError(
                {'available_copies': 'Available copies cannot exceed total copies.'}
            )
        return attrs
