from django.urls import path

from . import views

app_name = "apclasses"

urlpatterns = [
    path("", views.ap_event_list_view, name="event_list"),
    path("coming-soon/", views.coming_soon_view, name="coming_soon"),
    path("events/<slug:slug>/", views.ap_event_detail_view, name="event_detail"),
    path("events/<slug:slug>/start/", views.start_ap_event_view, name="start_event"),
    path("attempt/<uuid:token>/", views.ap_attempt_view, name="attempt"),
    path("attempt/<uuid:token>/result/", views.ap_event_result_view, name="event_result"),
    path("attempt/<uuid:token>/review/<int:question_id>/", views.ap_question_review_view, name="question_review"),
    path("attempt/<uuid:token>/submit/", views.submit_ap_attempt_view, name="submit_attempt"),
    path("attempt/<uuid:token>/frq-upload/", views.upload_frq_submission_view, name="frq_upload"),
]
