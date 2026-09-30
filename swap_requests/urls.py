from django.urls import path
from . import views

app_name = 'swap_requests'

urlpatterns = [
    path('', views.index, name='index'),
]