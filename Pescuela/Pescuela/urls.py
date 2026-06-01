from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from django.conf import settings
from django.conf.urls.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/', include('app_escuela.api.urls')),

    path('api/token/', TokenObtainPairView.as_view()),
    path('api/token/refresh/', TokenRefreshView.as_view()),
    path('accounts/', include('django.contrib.auth.urls')),
    path(
        'media/<path:path>',
        serve,
        {'document_root': settings.MEDIA_ROOT}
    ),
]
