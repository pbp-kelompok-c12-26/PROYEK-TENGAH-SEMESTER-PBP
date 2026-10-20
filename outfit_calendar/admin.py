
# Register your models here.
from django.contrib import admin

from .models import OutfitSchedule, ScheduledItem


class ScheduledItemInline(admin.TabularInline):
    model = ScheduledItem
    extra = 0


@admin.register(OutfitSchedule)
class OutfitScheduleAdmin(admin.ModelAdmin):
    list_display = ('date', 'outfit', 'user', 'note')
    list_filter = ('date',)
    inlines = [ScheduledItemInline]