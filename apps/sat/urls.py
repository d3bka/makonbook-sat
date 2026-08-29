from django.urls import path, include
from . import views, guest_views, test_import_views

urlpatterns = [
    path('', views.classroom_entry, name='sat_menu'),
    path('', views.home, name="home"),


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
    path('test-flow/draft/save/', views.save_test_module_draft, name='save_test_module_draft'),
    path('rankings/<str:pk>', views.rankings, name='rankings'),
    path('enter-code/', views.enter_secret_code, name='enter_secret_code'),
    path('start-makeup-test/<str:pk>/', views.start_makeup_test, name='start_makeup_test'),
    path('makeup-test-module/<str:pk>/', views.makeup_test_module, name='makeup_test_module'),

    path('dev/', include('apps.sat.urls_dev')),
    path('admin-panel/', include('apps.sat.urls_admin')),

    path('practice_tests/', views.practice_tests, name='practice_tests'),
    path('vocabulary/', views.vocabulary, name='vocabulary'),
    path('admissions/', views.admissions, name='admissions'),

    # Support teacher planning
    path('support-teachers/', views.support_teacher_list, name='support_teacher_list'),
    path('support-teachers/me/profile/', views.support_teacher_profile_edit, name='support_teacher_profile_edit'),
    path('support-teachers/me/availability/add/', views.support_teacher_availability_add, name='support_teacher_availability_add'),
    path('support-teachers/me/availability/<int:availability_id>/delete/', views.support_teacher_availability_delete, name='support_teacher_availability_delete'),
    path('support-teachers/me/planner/', views.support_teacher_planner, name='support_teacher_planner'),
    path('support-teachers/me/sessions/schedule/', views.schedule_support_topic_session, name='schedule_support_topic_session'),
    path('support-sessions/<int:session_id>/manage/', views.manage_support_session, name='manage_support_session'),
    path('manager/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/teachers/<int:teacher_id>/', views.manager_teacher_detail, name='manager_teacher_detail'),
    path('manager/classrooms/<int:classroom_id>/', views.manager_classroom_detail, name='manager_classroom_detail'),
    # Structured PDF test import / review
    path('test-imports/', test_import_views.test_import_list, name='test_import_list'),
    path('test-imports/new/', test_import_views.test_import_create, name='test_import_create'),
    path('test-imports/published/', test_import_views.managed_test_list, name='managed_test_list'),
    # Put the specific question route before the greedy <path:test_name> edit route.
    path('test-imports/published/<path:test_name>/questions/<str:section>/<int:question_id>/edit/', test_import_views.managed_test_question_edit, name='managed_test_question_edit'),
    path('test-imports/published/<path:test_name>/availability/', test_import_views.managed_test_toggle_availability, name='managed_test_toggle_availability'),
    path('test-imports/published/<path:test_name>/edit/', test_import_views.managed_test_edit, name='managed_test_edit'),
    path('test-imports/published/<path:test_name>/delete/', test_import_views.managed_test_delete, name='managed_test_delete'),
    path('test-imports/notifications/read/', test_import_views.test_import_notifications_read, name='test_import_notifications_read'),
    path('test-imports/clear-failed/', test_import_views.test_import_clear_failed, name='test_import_clear_failed'),
    path('test-imports/<int:job_id>/delete/', test_import_views.test_import_delete, name='test_import_delete'),
    path('test-imports/<int:job_id>/preview/', test_import_views.test_import_preview, name='test_import_preview'),
    path('test-imports/<int:job_id>/', test_import_views.test_import_detail, name='test_import_detail'),
    path('test-imports/<int:job_id>/process/', test_import_views.test_import_process, name='test_import_process'),
    path('test-imports/<int:job_id>/audit/batch/', test_import_views.test_import_audit_batch, name='test_import_audit_batch'),
    path('test-imports/<int:job_id>/status/', test_import_views.test_import_status, name='test_import_status'),
    path('test-imports/<int:job_id>/publish/', test_import_views.test_import_publish, name='test_import_publish'),
    path('test-imports/<int:job_id>/review/', test_import_views.test_import_review, name='test_import_review'),
    path('test-imports/<int:job_id>/source.pdf', test_import_views.test_import_pdf, name='test_import_pdf'),
    path('test-imports/<int:job_id>/questions/<int:question_id>/edit/', test_import_views.test_import_question_edit, name='test_import_question_edit'),
    path('support-teachers/<int:teacher_id>/', views.support_teacher_detail, name='support_teacher_detail'),
    path('support-teachers/<int:teacher_id>/book/', views.book_support_lesson, name='book_support_lesson'),
    path('support-lessons/', views.my_support_lessons, name='my_support_lessons'),
    path('support-lessons/<int:booking_id>/cancel/', views.cancel_support_lesson, name='cancel_support_lesson'),
    path('support-lessons/<int:booking_id>/feedback/', views.leave_support_lesson_feedback, name='leave_support_lesson_feedback'),
    path('support-lessons/<int:booking_id>/manage/', views.manage_support_lesson, name='manage_support_lesson'),

    path('vocabulary/practice-quiz/', views.vocabulary_practice_quiz, name='vocabulary_practice_quiz'),
    path('vocabulary/practice-quiz/start/', views.vocabulary_practice_quiz_start, name='vocabulary_practice_quiz_start'),
    path('vocabulary/practice-quiz/result/', views.vocabulary_practice_quiz_result, name='vocabulary_practice_quiz_result'),
    path('vocabulary/flashcards/mark/', views.vocabulary_flashcard_mark, name='vocabulary_flashcard_mark'),

    path('vocabulary/<slug:slug>/', views.vocabulary_section, name='vocabulary_section'),
    path('admissions/<slug:slug>/', views.admissions_section, name='admissions_section'),

    path('teacher/classrooms/', views.teacher_classroom_list, name='teacher_classroom_list'),
    path('teacher/classrooms/create/', views.create_classroom, name='create_classroom'),
    path('teacher/classrooms/<int:classroom_id>/', views.teacher_classroom_dashboard, name='teacher_classroom_dashboard'),
    path('teacher/classrooms/<int:classroom_id>/generate-code/', views.generate_classroom_join_code, name='generate_classroom_join_code'),

    path('join/', views.submit_classroom_join_request, name='submit_classroom_join_request'),
    path('join/status/', views.classroom_join_status, name='classroom_join_status'),
    path('student/goals/csrf/', views.student_goal_csrf, name='student_goal_csrf'),
    path('student/goals/', views.student_goal_settings, name='student_goal_settings'),
    path('classroom/<int:classroom_id>/', views.student_classroom_home, name='student_classroom_home'),
    path('classroom/<int:classroom_id>/goals/', views.student_goal_settings_legacy, name='student_goal_settings_legacy'),
    path('classroom/<int:classroom_id>/leave/', views.leave_classroom, name='leave_classroom'),

    path('teacher/classrooms/<int:classroom_id>/requests/', views.classroom_join_requests, name='classroom_join_requests'),
    path('teacher/classrooms/<int:classroom_id>/requests/<int:membership_id>/approve/', views.approve_join_request, name='approve_join_request'),
    path('teacher/classrooms/<int:classroom_id>/requests/<int:membership_id>/reject/', views.reject_join_request, name='reject_join_request'),

    path('teacher/classrooms/<int:classroom_id>/students/<int:user_id>/access/', views.update_student_section_access, name='update_student_section_access'),
    path('teacher/classrooms/<int:classroom_id>/students/<int:user_id>/remove/', views.remove_student_from_classroom, name='remove_student_from_classroom'),
    path('teacher/classrooms/<int:classroom_id>/section-access/', views.update_classroom_section_access, name='update_classroom_section_access'),

    path('classroom/<int:classroom_id>/ap-tests/', views.classroom_ap_tests, name='classroom_ap_tests'),
    path('teacher/classrooms/<int:classroom_id>/ap-tests/access/', views.update_classroom_ap_test_access, name='update_classroom_ap_test_access'),
    path('classroom/<int:classroom_id>/practice-tests/', views.classroom_practice_tests, name='classroom_practice_tests'),
    path('classroom/<int:classroom_id>/practice/<str:pk>/start/', views.classroom_start_practise, name='classroom_practise'),
    path('classroom/<int:classroom_id>/practice/<str:pk>/module/', views.classroom_module_test, name='classroom_test'),
    path('teacher/classrooms/<int:classroom_id>/practice-tests/access/', views.update_classroom_practice_test_access, name='update_classroom_practice_test_access'),

    path('classroom/<int:classroom_id>/vocabulary/', views.classroom_vocabulary, name='classroom_vocabulary'),
    path('classroom/<int:classroom_id>/vocabulary/<slug:slug>/', views.classroom_vocabulary_section, name='classroom_vocabulary_section'),
    path('classroom/<int:classroom_id>/vocabulary/practice-quiz/start/', views.classroom_vocabulary_practice_quiz_start, name='classroom_vocabulary_practice_quiz_start'),
    path('classroom/<int:classroom_id>/vocabulary/practice-quiz/result/', views.classroom_vocabulary_practice_quiz_result, name='classroom_vocabulary_practice_quiz_result'),
    path('classroom/<int:classroom_id>/vocabulary/flashcards/mark/', views.classroom_vocabulary_flashcard_mark, name='classroom_vocabulary_flashcard_mark'),
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
    path("global-events/attempt/<uuid:guest_token>/submit/status/", guest_views.global_event_submit_status_view, name="global_event_submit_status"),
    path("global-events/attempt/<uuid:guest_token>/result/", guest_views.global_event_result_view, name="global_event_result"),
<<<<<<< HEAD
    path("global-events/attempt/<uuid:guest_token>/review/", guest_views.global_event_review_view, name="global_event_review"),
    path(
        "global-events/attempt/<uuid:guest_token>/review/<str:section>/<str:module>/<int:id>/",
        guest_views.global_event_review_question_view,
        name="global_event_review_question",
    ),
=======
    path("global-events/attempt/<uuid:guest_token>/review/<str:section>/<str:module>/<int:question_id>/", guest_views.global_event_review_question_view, name="global_event_review_question"),
>>>>>>> 8bac338a46e0ea29b051683a0812ace0f67efd8d

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