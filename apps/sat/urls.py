from django.urls import path, include
from . import views, guest_views

urlpatterns = [
    path('', views.classroom_entry, name='sat_menu'),

    path('clear/<str:test>/<str:section>/<str:module>/', views.clear),
    path('practise/<str:pk>', views.start_Practise, name='practise'),
    path('restart/<str:pk>', views.restart, name='restart'),
    path('restart_section/<str:pk>/<str:section>/', views.restart_section, name='restart_section'),
    path('punishment/<str:pk>', views.punishment, name='punishment'),
    path('results/<str:test>', views.results, name='results'),
    path('results/certificate/<str:test>/', views.certificate, name='results_certificate'),
    path('results/certificate/<str:test>/<str:username>', views.certificate_by_user, name='results_certificate_by_user'),
    path('results/<str:test>/<str:username>', views.results_by_user, name='results_by_user'),
    path('question/<str:key>/<str:section>/<str:module>/<str:id>', views.question, name='question'),
    path('practise/<str:pk>/start', views.module_test, name='test'),
    path('check_the_answers', views.check_the_answers, name='check_the_answers'),
    path('rankings/<str:pk>', views.rankings, name='rankings'),
    path('enter-code/', views.enter_secret_code, name='enter_secret_code'),
    path('start-makeup-test/<str:pk>/', views.start_makeup_test, name='start_makeup_test'),
    path('makeup-test-module/<str:pk>/', views.makeup_test_module, name='makeup_test_module'),

    path('dev/', include('apps.sat.urls_dev')),
    path('admin-panel/', include('apps.sat.urls_admin')),

    path('practice_tests/', views.practice_tests, name='practice_tests'),
    path('vocabulary/', views.vocabulary, name='vocabulary'),
    path('admissions/', views.admissions, name='admissions'),

    path('vocabulary/practice-quiz/', views.vocabulary_practice_quiz, name='vocabulary_practice_quiz'),
    path('vocabulary/practice-quiz/start/', views.vocabulary_practice_quiz_start, name='vocabulary_practice_quiz_start'),
    path('vocabulary/practice-quiz/result/', views.vocabulary_practice_quiz_result, name='vocabulary_practice_quiz_result'),

    path('vocabulary/<slug:slug>/', views.vocabulary_section, name='vocabulary_section'),
    path('admissions/<slug:slug>/', views.admissions_section, name='admissions_section'),

    path('teacher/classrooms/', views.teacher_classroom_list, name='teacher_classroom_list'),
    path('teacher/classrooms/create/', views.create_classroom, name='create_classroom'),
    path('teacher/classrooms/<int:classroom_id>/', views.teacher_classroom_dashboard, name='teacher_classroom_dashboard'),
    path('teacher/classrooms/<int:classroom_id>/generate-code/', views.generate_classroom_join_code, name='generate_classroom_join_code'),

    path('join/', views.submit_classroom_join_request, name='submit_classroom_join_request'),
    path('join/status/', views.classroom_join_status, name='classroom_join_status'),
    path('classroom/<int:classroom_id>/', views.student_classroom_home, name='student_classroom_home'),

    path('teacher/classrooms/<int:classroom_id>/requests/', views.classroom_join_requests, name='classroom_join_requests'),
    path('teacher/classrooms/<int:classroom_id>/requests/<int:membership_id>/approve/', views.approve_join_request, name='approve_join_request'),
    path('teacher/classrooms/<int:classroom_id>/requests/<int:membership_id>/reject/', views.reject_join_request, name='reject_join_request'),

    path('teacher/classrooms/<int:classroom_id>/students/<int:user_id>/access/', views.update_student_section_access, name='update_student_section_access'),
    path('teacher/classrooms/<int:classroom_id>/students/<int:user_id>/remove/', views.remove_student_from_classroom, name='remove_student_from_classroom'),

    path('classroom/<int:classroom_id>/practice-tests/', views.classroom_practice_tests, name='classroom_practice_tests'),
    path('classroom/<int:classroom_id>/practice/<str:pk>/start/', views.classroom_start_practise, name='classroom_practise'),
    path('classroom/<int:classroom_id>/practice/<str:pk>/module/', views.classroom_module_test, name='classroom_test'),
    path('teacher/classrooms/<int:classroom_id>/practice-tests/access/', views.update_classroom_practice_test_access, name='update_classroom_practice_test_access'),

    path('classroom/<int:classroom_id>/vocabulary/', views.classroom_vocabulary, name='classroom_vocabulary'),
    path('classroom/<int:classroom_id>/admissions/', views.classroom_admissions, name='classroom_admissions'),

    path('teacher/classrooms/<int:classroom_id>/progress/', views.classroom_progress_dashboard, name='classroom_progress_dashboard'),
    path('teacher/classrooms/<int:classroom_id>/progress/student/<int:student_id>/practice/', views.classroom_student_practice_progress, name='classroom_student_practice_progress'),
    path('teacher/classrooms/<int:classroom_id>/progress/student/<int:student_id>/vocabulary/', views.classroom_student_vocab_progress, name='classroom_student_vocab_progress'),
    path('teacher/classrooms/<int:classroom_id>/progress/student/<int:student_id>/admissions/', views.classroom_student_admission_progress, name='classroom_student_admission_progress'),
    path('teacher/classrooms/<int:classroom_id>/progress/student/<int:student_id>/practice/<str:test_name>/review/', views.classroom_student_review_results, name='classroom_student_review_results'),
    path('teacher/classrooms/<int:classroom_id>/progress/student/<int:student_id>/review/<str:key>/<str:section>/<str:module>/<str:id>/', views.classroom_student_review_question, name='classroom_student_review_question'),

    path('classroom/<int:classroom_id>/chat/', views.classroom_chat, name='classroom_chat'),
    path('classroom/<int:classroom_id>/chat/send/', views.send_classroom_message, name='send_classroom_message'),
    path('classroom/<int:classroom_id>/chat/fetch/', views.fetch_classroom_messages, name='fetch_classroom_messages'),
    path('classroom/<int:classroom_id>/chat/message/<int:message_id>/delete/', views.delete_classroom_message, name='delete_classroom_message'),
    path('classroom/<int:classroom_id>/chat/message/<int:message_id>/delete-file/', views.delete_classroom_message_file, name='delete_classroom_message_file'),


    path('teacher/classrooms/<int:classroom_id>/delete/', views.delete_classroom, name='delete_classroom'),
    path('teacher/classrooms/<int:classroom_id>/edit/', views.edit_classroom, name='edit_classroom'),


    #GUEST URLS
    path("guest/", guest_views.guest_entry_view, name="guest_entry"),
    path("guest/logout/", guest_views.guest_logout_view, name="guest_logout"),

    path("global-events/", guest_views.global_event_list_view, name="global_event_list"),
    path("global-events/<slug:slug>/", guest_views.global_event_detail_view, name="global_event_detail"),
    path("global-events/<slug:slug>/start/", guest_views.start_global_event_view, name="start_global_event"),

    path("global-events/attempt/<uuid:guest_token>/", guest_views.global_event_attempt_view, name="global_event_attempt"),
    path("global-events/attempt/<uuid:guest_token>/save/", guest_views.save_global_event_answer_view, name="save_global_event_answer"),
    path("global-events/attempt/<uuid:guest_token>/submit/", guest_views.submit_global_event_view, name="submit_global_event"),
    path("global-events/attempt/<uuid:guest_token>/result/", guest_views.global_event_result_view, name="global_event_result"),

    path("global-events/<slug:slug>/leaderboard/", guest_views.global_event_leaderboard_view, name="global_event_leaderboard"),

    #Teacher Vocabulary Management
    path('teacher/vocabulary/', views.teacher_vocabulary_units, name='teacher_vocabulary_units'),
    path('teacher/vocabulary/create-unit/', views.create_vocabulary_unit, name='create_vocabulary_unit'),
    path('teacher/vocabulary/unit/<int:unit_id>/', views.teacher_vocabulary_unit_detail, name='teacher_vocabulary_unit_detail'),
    path('teacher/vocabulary/unit/<int:unit_id>/add-word/', views.create_vocabulary_word, name='create_vocabulary_word'),
    path('teacher/vocabulary/unit/<int:unit_id>/add-question/', views.create_vocabulary_question, name='create_vocabulary_question'),
    path('teacher/vocabulary/bulk-import/', views.bulk_import_vocabulary_words, name='bulk_import_vocabulary_words'),

    path('teacher/classrooms/<int:classroom_id>/students/<int:user_id>/practice-tests/access/',views.update_student_practice_test_access,name='update_student_practice_test_access'),
]