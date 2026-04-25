from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('apps.base.urls')),
    path('sat/', include('apps.sat.urls')),
    path('ap-classes/admin-panel/', RedirectView.as_view(pattern_name='apclasses:event_list', permanent=False), name='ap_admin_exam_list'),
    path('ap-classes/', include('apps.apclasses.urls')),
    path('admin/', admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
