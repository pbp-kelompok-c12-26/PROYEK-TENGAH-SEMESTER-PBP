from django.urls import path
from . import views

app_name = 'outfit_calendar'

urlpatterns = [
    path('', views.index, name='index'),
    path('add/', views.schedule_create, name='schedule_create'),
    path('<int:pk>/', views.schedule_detail, name='schedule_detail'),
    path('<int:pk>/edit/', views.schedule_update, name='schedule_update'),
    path('<int:pk>/delete/', views.schedule_delete, name='schedule_delete'),
]