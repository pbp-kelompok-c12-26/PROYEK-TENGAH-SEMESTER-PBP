from django.urls import path
from home import views

app_name = 'home'

urlpatterns = [
    path('', views.index, name='index'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('onboarding/skip/', views.onboarding_skip, name='onboarding_skip'),
]
