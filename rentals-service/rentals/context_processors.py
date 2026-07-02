def user_cache(request):
    if getattr(request.user, 'is_authenticated', False):
        from .models import UserCache
        return {'user_cache': UserCache.objects.filter(user_id=request.user.id).first()}
    return {'user_cache': None}
