from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.menu_page, name='sat_menu'),

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
]