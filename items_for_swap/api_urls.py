from django.urls import path

from . import api_views

app_name = 'items_for_swap_api'

urlpatterns = [
    path('', api_views.listing_list, name='listing-list'),
    path('mine/', api_views.my_listing_list, name='my-listings'),
    path('<int:pk>/', api_views.listing_detail, name='listing-detail'),
]
