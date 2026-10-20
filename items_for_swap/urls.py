from django.urls import path

from . import views

app_name = 'items_for_swap'

urlpatterns = [
    path('', views.index, name='index'),
    path('add/', views.add, name='add'),
    path('add/<int:pk>/', views.add, name='list_item'),      # pk = ClothingItem (tombol "List for Swap")
    path('<int:pk>/', views.detail, name='detail'),          # pk = ItemForSwap
    path('<int:pk>/edit/', views.edit, name='edit'),
    path('<int:pk>/return/', views.return_item, name='return_item'),
]