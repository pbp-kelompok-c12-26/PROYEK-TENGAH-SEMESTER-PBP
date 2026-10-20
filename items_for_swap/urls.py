from django.urls import path
from . import views

app_name = 'items_for_swap'

urlpatterns = [
    path('', views.index, name='index'),
]