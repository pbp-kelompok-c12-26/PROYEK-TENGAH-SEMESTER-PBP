from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path('accounts/', include('accounts.urls')),
    path('digital-wardrobe/', include('digital_wardrobe.urls')),
    path('items-for-swap/', include('items_for_swap.urls')),
    path('swap-requests/', include('swap_requests.urls')),
    path('outfit-calendar/', include('outfit_calendar.urls')),

    # Menyajikan foto upload (media); dipakai juga saat DEBUG = False
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    path('auth/', include('accounts.urls')),
    path('calendar/', include('outfit_calendar.urls')),
]