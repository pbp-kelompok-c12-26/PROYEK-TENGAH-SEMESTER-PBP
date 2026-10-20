from django.urls import path
from . import views

app_name = 'swap_requests'

urlpatterns = [
    path('', views.index, name='index'),
    path('new/', views.create, name='create'),                       # ?item=<id pakaian yang diminta>
    path('item/<int:item_id>/', views.item_requests, name='item_requests'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/sent/', views.sent, name='sent'),
    path('<int:pk>/edit/', views.update, name='update'),
    path('<int:pk>/respond/', views.respond, name='respond'),
    path('<int:pk>/confirm/', views.confirm, name='confirm'),
    path('<int:pk>/delete/', views.delete, name='delete'),
]
