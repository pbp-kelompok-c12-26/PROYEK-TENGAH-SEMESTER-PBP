from django.urls import path

from . import api_views

app_name = 'swap_requests_api'

urlpatterns = [
    path('', api_views.swap_request_list, name='request-list'),
    path('<int:pk>/', api_views.swap_request_detail, name='request-detail'),
    path('<int:pk>/respond/', api_views.swap_request_respond, name='request-respond'),
    path('<int:pk>/confirm/', api_views.swap_request_confirm, name='request-confirm'),
    path('bulk-delete/', api_views.swap_request_bulk_delete, name='request-bulk-delete'),
]
