from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from rest_framework import viewsets, permissions

from .models import Book
from .serializers import BookSerializer


def book_list(request):
    query = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '').strip()

    books = Book.objects.all()
    if query:
        books = books.filter(Q(title__icontains=query) | Q(author__icontains=query))
    if genre:
        books = books.filter(genre__icontains=genre)

    genres = Book.objects.exclude(genre='').values_list('genre', flat=True).distinct().order_by('genre')

    return render(request, 'books/book_list.html', {
        'books': books,
        'query': query,
        'genre': genre,
        'genres': genres,
    })


def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)

    user_has_this_book = False
    can_borrow = False
    borrow_error = None

    if request.user.is_authenticated:
        from rentals.services import can_borrow as check_can_borrow, check_overdue_and_suspend
        from rentals.models import BorrowRecord

        check_overdue_and_suspend(request.user)
        request.user.profile.refresh_from_db()

        user_has_this_book = BorrowRecord.objects.filter(
            user=request.user,
            book=book,
            status__in=['active', 'extended', 'overdue'],
        ).exists()

        ok, error = check_can_borrow(request.user, book)
        can_borrow = ok
        borrow_error = error

    return render(request, 'books/book_detail.html', {
        'book': book,
        'user_has_this_book': user_has_this_book,
        'can_borrow': can_borrow,
        'borrow_error': borrow_error,
    })


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
