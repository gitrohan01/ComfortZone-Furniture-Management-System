from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from store.views import CustomerTokenView, register_customer
urlpatterns = [path('django-admin/', admin.site.urls), path('api/auth/login/', CustomerTokenView.as_view(), name='token_obtain_pair'), path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'), path('api/register/', register_customer, name='register_customer'), path('api/', include('store.urls'))]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
