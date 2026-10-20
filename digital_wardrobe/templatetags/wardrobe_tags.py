from django import template

from digital_wardrobe.models import ClothingItem

register = template.Library()


@register.simple_tag
def swap_item_count(user):
    """
    Jumlah pakaian milik user yang sedang ditawarkan di Items for Swap.
    Pemakaian di template:
        {% load wardrobe_tags %}
        {% swap_item_count user as swap_count %}
    """
    if not getattr(user, 'is_authenticated', False):
        return 0
    return ClothingItem.objects.listed_for_swap(user).count()
