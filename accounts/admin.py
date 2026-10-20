from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'phone_number', 'domicile', 'onboarding_completed')
    list_filter = ('onboarding_completed',)
    search_fields = ('user__username', 'display_name', 'phone_number')
