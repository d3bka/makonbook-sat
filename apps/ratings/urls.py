from django.urls import path

from . import views

urlpatterns = [
    path("", views.rating_home, name="rating_home"),
    path("student/<int:student_id>/", views.public_student, name="rating_public_student"),
    path("parent/", views.parent_lookup, name="rating_parent_lookup"),
    path("teacher/classroom/<int:classroom_id>/", views.teacher_classroom_ratings, name="rating_teacher_classroom"),
    path("teacher/classroom/<int:classroom_id>/student/<int:student_id>/", views.assess_student, name="rating_assess_student"),
    path("teacher/assessment/<int:assessment_id>/edit/", views.edit_assessment, name="rating_edit_assessment"),
]
