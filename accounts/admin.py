from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'onboarding_completed', 'created_at')
    list_filter = ('onboarding_completed',)
    search_fields = ('user__username', 'display_name')
