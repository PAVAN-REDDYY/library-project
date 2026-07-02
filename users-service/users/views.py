from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .auth_utils import issue_jwt_cookie
from .forms import RegistrationForm, LoginForm


def register(request):
    if request.user.is_authenticated:
        return redirect(settings.RENTALS_SERVICE_PUBLIC_URL + '/')
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            name = user.first_name or user.username
            messages.success(request, f'Welcome to the library, {name}! Your account is ready.')
            response = redirect(settings.RENTALS_SERVICE_PUBLIC_URL + '/')
            issue_jwt_cookie(response, user)
            return response
    else:
        form = RegistrationForm()
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(settings.RENTALS_SERVICE_PUBLIC_URL + '/')
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
                # Cross-service `next` params (from books-service/rentals-service's
                # LOGIN_URL redirects) already arrive fully-qualified, so just
                # redirect straight there; otherwise fall back to rentals-service's
                # home page since there's no local `home` URL in this service.
                next_url = request.GET.get('next') or (settings.RENTALS_SERVICE_PUBLIC_URL + '/')
                response = redirect(next_url)
                issue_jwt_cookie(response, user)
                return response
            messages.error(request, 'Invalid username or password. Please try again.')
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    # Accepts any method (not just POST): books-service's/rentals-service's
    # nav bars link to logout as a plain GET link, since a real cross-origin
    # CSRF-protected POST isn't possible without a shared-origin gateway,
    # which doesn't exist here. Accepted, deliberate trade-off.
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    response = redirect(settings.RENTALS_SERVICE_PUBLIC_URL + '/')
    response.delete_cookie('access_token')
    return response


@login_required
def profile(request):
    return render(request, 'users/profile.html', {'profile': request.user.profile})
