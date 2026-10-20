from django.contrib import admin

from .models import ItemForSwap


@admin.register(ItemForSwap)
class ItemForSwapAdmin(admin.ModelAdmin):
    list_display = ('clothing_item', 'user', 'status', 'meeting_location', 'posted_at')
    list_filter = ('status', 'posted_at')
    search_fields = ('clothing_item__name', 'user__username', 'meeting_location')
    raw_id_fields = ('clothing_item', 'user')
    readonly_fields = ('posted_at',)
    # Flag is_listed_for_swap diurus model (save) dan signal (delete),
    # jadi tambah/hapus lewat admin tetap konsisten.