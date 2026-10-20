from django.contrib import admin

from .models import SwapRequest


@admin.register(SwapRequest)
class SwapRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'requester', 'offered_item_name', 'owner', 'requested_item_name', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('requester__username', 'owner__username', 'offered_item_name', 'requested_item_name')
