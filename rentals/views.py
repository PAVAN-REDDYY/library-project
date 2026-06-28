from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from books.models import Book
from .models import BorrowRecord
from .serializers import BorrowRecordSerializer
from . import services


def home(request):
    from books.models import Book as BookModel
    total_books = BookModel.objects.count()
    available_books = BookModel.objects.filter(available_copies__gt=0).count()
    active_borrows = BorrowRecord.objects.filter(status__in=['active', 'extended']).count()
    overdue_borrows = BorrowRecord.objects.filter(status='overdue').count()
    recent_borrows = BorrowRecord.objects.select_related('user', 'book').order_by('-created_at')[:6]

    context = {
        'total_books': total_books,
        'available_books': available_books,
        'active_borrows': active_borrows,
        'overdue_borrows': overdue_borrows,
        'recent_borrows': recent_borrows,
    }
    return render(request, 'rentals/home.html', context)


@login_required
def my_borrows(request):
    services.check_overdue_and_suspend(request.user)
    request.user.profile.refresh_from_db()

    active = BorrowRecord.objects.filter(
        user=request.user,
        status__in=['active', 'extended', 'overdue'],
    ).select_related('book').order_by('due_date')

    history = BorrowRecord.objects.filter(
        user=request.user,
        status='returned',
    ).select_related('book').order_by('-return_date')

    return render(request, 'rentals/my_borrows.html', {
        'active': active,
        'history': history,
    })


@login_required
def borrow_book_view(request, book_id):
    if request.method != 'POST':
        return redirect('books:detail', pk=book_id)

    book = get_object_or_404(Book, pk=book_id)
    try:
        services.borrow_book(request.user, book)
        messages.success(request, f'You have borrowed "{book.title}". Return it within 14 days.')
    except ValueError as exc:
        messages.error(request, str(exc))

    return redirect('books:detail', pk=book_id)


@login_required
def return_book_view(request, record_id):
    if request.method != 'POST':
        return redirect('rentals:my_borrows')

    record = get_object_or_404(BorrowRecord, pk=record_id, user=request.user)
    try:
        services.return_book(record)
        messages.success(request, f'"{record.book.title}" has been returned. Thank you!')
    except ValueError as exc:
        messages.error(request, str(exc))

    return redirect('rentals:my_borrows')


@login_required
def extend_borrow_view(request, record_id):
    if request.method != 'POST':
        return redirect('rentals:my_borrows')

    record = get_object_or_404(BorrowRecord, pk=record_id, user=request.user)
    try:
        services.extend_borrow(record)
        messages.success(
            request,
            f'Extension granted for "{record.book.title}". New due date: {record.extended_due_date}.'
        )
    except ValueError as exc:
        messages.error(request, str(exc))

    return redirect('rentals:my_borrows')


# ── REST API ────────────────────────────────────────────────────────────────

class BorrowRecordViewSet(viewsets.ModelViewSet):
    serializer_class = BorrowRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return BorrowRecord.objects.select_related('user', 'book').all()
        return BorrowRecord.objects.select_related('user', 'book').filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def return_book(self, request, pk=None):
        record = self.get_object()
        try:
            services.return_book(record)
            return Response(BorrowRecordSerializer(record).data)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)

    @action(detail=True, methods=['post'])
    def extend(self, request, pk=None):
        record = self.get_object()
        try:
            services.extend_borrow(record)
            return Response(BorrowRecordSerializer(record).data)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)

    @action(detail=False, methods=['post'])
    def borrow(self, request):
        book_id = request.data.get('book_id')
        if not book_id:
            return Response({'error': 'book_id is required.'}, status=400)
        book = get_object_or_404(Book, pk=book_id)
        try:
            record = services.borrow_book(request.user, book)
            return Response(BorrowRecordSerializer(record).data, status=201)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
