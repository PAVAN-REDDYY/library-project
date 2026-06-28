from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import RegistrationForm, LoginForm


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            name = user.first_name or user.username
            messages.success(request, f'Welcome to the library, {name}! Your account is ready.')
            return redirect('home')
    else:
        form = RegistrationForm()
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user:
                login(request, user)
                next_url = request.GET.get('next') or 'home'
                return redirect(next_url)
            messages.error(request, 'Invalid username or password. Please try again.')
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.info(request, 'You have been logged out successfully.')
    return redirect('home')


@login_required
def profile(request):
    from rentals.services import check_overdue_and_suspend
    from rentals.models import BorrowRecord

    check_overdue_and_suspend(request.user)
    request.user.profile.refresh_from_db()

    active_borrows = BorrowRecord.objects.filter(
        user=request.user,
        status__in=['active', 'extended', 'overdue'],
    ).select_related('book').order_by('due_date')

    history = BorrowRecord.objects.filter(
        user=request.user,
        status='returned',
    ).select_related('book').order_by('-return_date')[:10]

    return render(request, 'users/profile.html', {
        'active_borrows': active_borrows,
        'history': history,
    })
