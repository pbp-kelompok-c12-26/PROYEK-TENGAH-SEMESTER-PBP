from django.urls import path

from . import api_views

app_name = 'home_api'

urlpatterns = [
    path('items-for-swap/<int:listing_id>/like/', api_views.like_toggle, name='like-toggle'),
]
