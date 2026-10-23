from django.urls import path
from home import views

app_name = 'home'

urlpatterns = [
    path('', views.index, name='index'),
    path('liked/', views.liked_items, name='liked_items'),
    path('liked/<int:listing_id>/toggle/', views.toggle_like, name='toggle_like'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('onboarding/skip/', views.onboarding_skip, name='onboarding_skip'),
]
