from django.contrib import admin

from .models import ClothingItem, Outfit


@admin.register(ClothingItem)
class ClothingItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'category', 'size', 'shoe_size', 'condition', 'is_listed_for_swap', 'created_at')
    list_filter = ('category', 'condition', 'gender', 'is_listed_for_swap', 'is_idle')
    search_fields = ('name', 'user__username')

@admin.register(Outfit)
class OutfitAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    search_fields = ('name', 'user__username')
    filter_horizontal = ('items',)
