from django.urls import path
from home import views

app_name = 'home'

urlpatterns = [
    path('', views.index, name='index'),
    path('onboarding/', views.onboarding_1, name='onboarding'),
    path("onboarding/profile/", views.onboarding_2, name="onboarding_2"),
    path("onboarding/sizes/", views.onboarding_3, name="onboarding_3"),
]
