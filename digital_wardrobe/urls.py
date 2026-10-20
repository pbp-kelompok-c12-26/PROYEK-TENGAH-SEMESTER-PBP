from django.urls import path
from . import views

app_name = 'digital_wardrobe'

urlpatterns = [
    path('', views.index, name='index'),
    path('items/', views.item_list, name='item_list'),
    path('items/add/', views.item_create, name='item_create'),
    path('items/<int:pk>/', views.item_detail, name='item_detail'),
    path('items/<int:pk>/edit/', views.item_update, name='item_update'),
    path('items/<int:pk>/delete/', views.item_delete, name='item_delete'),

    path('outfits/add/', views.outfit_create, name='outfit_create'),
    path('outfits/<int:pk>/', views.outfit_detail, name='outfit_detail'),
    path('outfits/<int:pk>/edit/', views.outfit_update, name='outfit_update'),
    path('outfits/<int:pk>/delete/', views.outfit_delete, name='outfit_delete'),
]
