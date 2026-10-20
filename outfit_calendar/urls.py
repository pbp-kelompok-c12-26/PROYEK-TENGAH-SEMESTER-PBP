from django.urls import path
from . import views

app_name = 'outfit_calendar'

urlpatterns = [
    path('', views.index, name='index'),
]