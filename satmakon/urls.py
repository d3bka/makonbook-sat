from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.views.decorators.cache import cache_control
from django.views.generic import RedirectView, TemplateView
from apps.base import error_views
from apps.base.sitemaps import sitemaps

urlpatterns = [
    path(
        "robots.txt",
        cache_control(max_age=60 * 60 * 24)(
            TemplateView.as_view(
                template_name="robots.txt",
                content_type="text/plain",
                extra_context={"sitemap_url": f"{settings.SITE_URL}/sitemap.xml"},
            )
        ),
        name="robots_txt",
    ),
    path(
        "sitemap.xml",
        cache_control(max_age=60 * 60 * 6)(sitemap),
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),

    path("practices", RedirectView.as_view(url="/sat/practice_tests/", permanent=False), name="practices_alias_no_slash"),
    path("practices/", RedirectView.as_view(url="/sat/practice_tests/", permanent=False), name="practices_alias"),
    path("practice-tests", RedirectView.as_view(url="/sat/practice_tests/", permanent=False), name="practice_tests_alias_no_slash"),
    path("practice-tests/", RedirectView.as_view(url="/sat/practice_tests/", permanent=False), name="practice_tests_alias"),
    path("accounts/", include("allauth.urls")),

    path("", include("apps.base.urls")),
    path("sat/", include("apps.sat.urls")),
    path("rating/", include("apps.ratings.urls")),
    path("ap-classes/admin-panel/", RedirectView.as_view(pattern_name="apclasses:event_list", permanent=False), name="ap_admin_exam_list"),
    path("ap-classes/", include("apps.apclasses.urls")),
    path("admin/", admin.site.urls),
]


handler400 = error_views.bad_request
handler403 = error_views.permission_denied
handler404 = error_views.page_not_found
handler500 = error_views.server_error
