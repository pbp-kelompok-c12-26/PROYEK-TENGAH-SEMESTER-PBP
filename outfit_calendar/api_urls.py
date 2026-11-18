from django.urls import path

from . import api_views

app_name = 'outfit_calendar_api'

urlpatterns = [
    path('schedules/', api_views.schedule_list, name='schedule-list'),
    path('schedules/<int:pk>/', api_views.schedule_detail, name='schedule-detail'),
]
