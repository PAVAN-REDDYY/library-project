from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ['phone', 'is_suspended', 'suspension_reason']


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_suspended_display', 'is_staff']
    list_filter = ['is_staff', 'is_superuser', 'profile__is_suspended']

    def is_suspended_display(self, obj):
        try:
            return obj.profile.is_suspended
        except UserProfile.DoesNotExist:
            return False
    is_suspended_display.boolean = True
    is_suspended_display.short_description = 'Suspended'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(UserProfile)
