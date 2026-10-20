from django.contrib import admin
from django.urls import path, include
from accounts import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path('accounts/', include('accounts.urls')),
    path('digital-wardrobe/', include('digital_wardrobe.urls')),
    path('items-for-swap/', include('items_for_swap.urls')),
    path('swap-requests/', include('swap_requests.urls')),
    path('outfit-calendar/', include('outfit_calendar.urls')),
]