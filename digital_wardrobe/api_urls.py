from django.urls import path

from . import api_views

app_name = 'digital_wardrobe_api'

urlpatterns = [
    path('items/', api_views.clothing_item_list, name='item-list'),
    path('items/bulk-delete/', api_views.clothing_item_bulk_delete, name='item-bulk-delete'),
    path('items/<int:pk>/', api_views.clothing_item_detail, name='item-detail'),
    path('outfits/', api_views.outfit_list, name='outfit-list'),
    path('outfits/<int:pk>/', api_views.outfit_detail, name='outfit-detail'),
]
