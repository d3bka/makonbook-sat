from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from apps.base import error_views

urlpatterns = [
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
