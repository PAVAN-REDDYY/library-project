from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import BorrowRecord, BookCache, UserCache
from .serializers import BorrowRecordSerializer
from . import services


def _attach_book_cache(records):
    book_ids = {r.book_id for r in records}
    cache_map = {bc.book_id: bc for bc in BookCache.objects.filter(book_id__in=book_ids)}
    for r in records:
        r.book_cache = cache_map.get(r.book_id)
    return records


def home(request):
    total_books = BookCache.objects.count()
    # Sum of remaining copies across the catalog, not a count of distinct
    # titles that still have >0 copies - the latter only drops once a title's
    # stock fully depletes to zero, so borrowing from any multi-copy title
    # left this number looking frozen even as books were actively checked out.
    available_books = BookCache.objects.aggregate(total=Sum('available_copies'))['total'] or 0
    active_borrows = BorrowRecord.objects.filter(status__in=['active', 'extended']).count()
    overdue_borrows = BorrowRecord.objects.filter(status='overdue').count()

    # Staff-only: this lists who borrowed what, so showing it on the public
    # home page (previously with no check at all) let any visitor - including
    # other logged-in patrons - see every other patron's borrowing activity
    # and identity. Only library staff get this operational view; everyone
    # else just sees the aggregate counts above.
    recent_borrows = []
    if request.user.is_authenticated and request.user.is_staff:
        recent_borrows = list(BorrowRecord.objects.order_by('-created_at')[:6])
        _attach_book_cache(recent_borrows)
        user_ids = {r.user_id for r in recent_borrows}
        user_map = {uc.user_id: uc for uc in UserCache.objects.filter(user_id__in=user_ids)}
        for r in recent_borrows:
            r.user_cache = user_map.get(r.user_id)

    return render(request, 'rentals/home.html', {
        'total_books': total_books,
        'available_books': available_books,
        'active_borrows': active_borrows,
        'overdue_borrows': overdue_borrows,
        'recent_borrows': recent_borrows,
    })


@login_required
def my_borrows(request):
    services.check_overdue_and_suspend(request.user.id)

    active = list(BorrowRecord.objects.filter(
        user_id=request.user.id, status__in=['pending', 'active', 'extended', 'overdue'],
    ).order_by('due_date'))
    history = list(BorrowRecord.objects.filter(
        user_id=request.user.id, status__in=['returned', 'rejected'],
    ).order_by('-updated_at'))
    _attach_book_cache(active)
    _attach_book_cache(history)

    return render(request, 'rentals/my_borrows.html', {'active': active, 'history': history})


@login_required
def borrow_book_view(request, book_id):
    """GET shows a confirmation page (this is the landing point for the plain
    GET link books-service's book_detail page uses instead of posting a form
    directly - a cross-origin form submission can't pass CSRF validation here
    without a shared gateway, which is out of scope; a top-level GET
    navigation has no such problem, and this page's own POST form is entirely
    same-origin). POST actually executes the borrow."""
    book_cache = get_object_or_404(BookCache, book_id=book_id)

    if request.method == 'POST':
        try:
            services.borrow_book(request.user.id, book_id)
            messages.success(request, f'You have borrowed "{book_cache.title}". Return it within 14 days.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('rentals:my_borrows')

    ok, error = services.can_borrow(request.user.id, book_id)
    return render(request, 'rentals/borrow_confirm.html', {
        'book': book_cache, 'can_borrow': ok, 'error': error,
    })


@login_required
def return_book_view(request, record_id):
    if request.method != 'POST':
        return redirect('rentals:my_borrows')
    record = get_object_or_404(BorrowRecord, pk=record_id, user_id=request.user.id)
    try:
        services.return_book(record)
        messages.success(request, 'Book returned. Thank you!')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('rentals:my_borrows')


@login_required
def extend_borrow_view(request, record_id):
    if request.method != 'POST':
        return redirect('rentals:my_borrows')
    record = get_object_or_404(BorrowRecord, pk=record_id, user_id=request.user.id)
    try:
        services.extend_borrow(record)
        messages.success(request, f'Extension granted. New due date: {record.extended_due_date}.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('rentals:my_borrows')


class BorrowRecordViewSet(viewsets.ModelViewSet):
    serializer_class = BorrowRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return BorrowRecord.objects.all()
        return BorrowRecord.objects.filter(user_id=self.request.user.id)

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
        try:
            record = services.borrow_book(request.user.id, int(book_id))
            return Response(BorrowRecordSerializer(record).data, status=201)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
