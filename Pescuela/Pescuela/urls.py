from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/', include('app_escuela.api.urls')),


    path(
        'media/<path:path>',
        serve,
        {'document_root': settings.MEDIA_ROOT}
    ),
]
