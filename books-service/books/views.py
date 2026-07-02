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
    return render(request, 'books/book_detail.html', {'book': book})


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
