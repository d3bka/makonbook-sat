from multiprocessing import context
from urllib import request

from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, HttpResponseRedirect, Http404, JsonResponse
from apps.base.decorators import allowed_users
from django.contrib.auth.models import Group, User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from satmakon.settings import BASE_DIR
from .libs import calculator
from django.utils import timezone
from datetime import timedelta
from .libs.certificate.certificate import create_certificate
from math import floor, ceil
from django.contrib import messages  # Added for user feedback
from apps.base.models import UserProfile
from django.core.cache import cache
from django.db.models import Q
import json
import random
import re
import uuid
from django.db.models import Count
from django.db import transaction
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from collections import defaultdict
from django.urls import reverse
from django.db import close_old_connections
from django.contrib.auth import authenticate, login, logout

try:
    from apps.apclasses.models import APExamEvent
except Exception:  # keeps SAT views import-safe if AP app is unavailable
    APExamEvent = None


def home(request):

    if request.user.is_authenticated:
        return redirect('dashboard')

    return render(request, "landing/home.html")



def loginPage(request):

    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:

            login(request, user)

            return redirect("dashboard")

    return render(request, "login.html")



@login_required(login_url='/login/')
def dashboard(request):

    return render(request, "dashboard.html")



def logoutUser(request):

    logout(request)

    return redirect("home")

def custom_round(number, base=0.4):
    if number % 1 >= base:
        return ceil(number)
    else:
        return floor(number)

@login_required(login_url='/login/')
@require_POST
def restart(request, pk):
    close_old_connections()

    user = request.user

    test = Test.objects.filter(name=pk).first()

    if not test:
        return HttpResponse(f"Test '{pk}' not found")

    if not user_has_test_access(user, test):
        return HttpResponse(
            f"Test '{pk}' is not assigned to your account.",
            status=403
        )

    stage, _ = TestStage.objects.get_or_create(
        user=user,
        test=test,
        defaults={"stage": 1}
    )

    # Try to restart the full test
    response = stage.resolve()

    if response:
        # Restart successful
        return render(request, 'sat/restart_success.html', {
            'test_name': pk,
            'section': None
        })
    else:
        # Retake limit exceeded
        user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'
        
        return render(request, 'sat/retake_limit_exceeded.html', {
            'test_name': pk,
            'section': None,
            'retakes_used': stage.retake_count,
            'max_retakes': stage.get_max_retakes(),
            'user_group': user_group
        })


def normalize_written_value(value):
    if value is None:
        return None

    value = str(value).strip().replace(' ', '')
    if value == '':
        return None

    # normalize commas if user uses decimal comma
    value = value.replace(',', '.')

    # try fraction first: 6/2 == 3
    if '/' in value:
        try:
            return Decimal(Fraction(value))
        except Exception:
            pass

    # then regular numeric values: 3, 03, 3.0, +3
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return value.lower()


from decimal import Decimal, InvalidOperation
from fractions import Fraction
from collections import defaultdict


def _normalize_written_token(value):
    if value is None:
        return None

    value = str(value).strip().replace(' ', '')
    if value == '':
        return None

    value = value.replace(',', '.')

    # fraction support, including forms like 10/-2 or -10/-2
    if '/' in value:
        try:
            parts = value.split('/')
            if len(parts) == 2:
                numerator = Decimal(parts[0])
                denominator = Decimal(parts[1])

                if denominator == 0:
                    return None

                return numerator / denominator
        except Exception:
            pass

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return value.lower()


def check_written(response, answer):
    if response is None or answer is None:
        return False

    response = str(response).strip()
    answer = str(answer).strip()

    if not response or not answer:
        return False

    response_options = [item.strip() for item in response.split(',') if item.strip()]
    answer_options = [item.strip() for item in answer.split(',') if item.strip()]

    normalized_responses = [_normalize_written_token(item) for item in response_options]
    normalized_answers = [_normalize_written_token(item) for item in answer_options]

    for res in normalized_responses:
        for ans in normalized_answers:
            if res == ans:
                return True

    return False


@allowed_users(['Admin', 'Tester'])
def tester_view(request):
    tests = Test.objects.all()
    return render(request, 'test/dashboard.html', {'tests': tests})


def is_member(user, names):
    for name in names:
        if user.groups.filter(name__iexact=name).exists():
            return True
    return False


def _normalize_test_section(section):
    return str(section or '').strip().lower()


def _normalize_test_module(module):
    module = str(module or '').strip().lower()
    if module in ['module_1', 'module-1', 'module 1', '1']:
        return 'm1'
    if module in ['module_2', 'module-2', 'module 2', '2']:
        return 'm2'
    return module


def _module_db_name(module):
    module = _normalize_test_module(module)
    if module == 'm1':
        return 'module_1'
    if module == 'm2':
        return 'module_2'
    return module


def _approved_student_memberships(user):
    if not user.is_authenticated:
        return ClassroomMembership.objects.none()
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved',
        classroom__is_active=True,
    ).select_related('classroom').prefetch_related('section_access')


def _first_classroom_membership_for_section(user, section):
    for membership in _approved_student_memberships(user):
        if get_membership_section_access_map(membership).get(section):
            return membership
    return None


def _user_is_restricted_classroom_student(user):
    return _approved_student_memberships(user).exists() and not is_teacher(user)


def _redirect_or_deny_classroom_section(request, section, route_name, denied_message):
    if not _user_is_restricted_classroom_student(request.user):
        return None

    membership = _first_classroom_membership_for_section(request.user, section)
    if not membership:
        return classroom_access_denied(request, message=denied_message)

    return redirect(route_name, classroom_id=membership.classroom_id)


def _validate_regular_module_answers(test_obj, section, module, answers):
    section = _normalize_test_section(section)
    module = _normalize_test_module(module)
    module_db = _module_db_name(module)

    if section not in ['english', 'math'] or module not in ['m1', 'm2']:
        return False, 'Invalid section/module.', []

    question_model = English_Question if section == 'english' else Math_Question
    expected_ids = set(
        question_model.objects.filter(test=test_obj, module=module_db).values_list('id', flat=True)
    )

    if not expected_ids:
        return False, 'No questions exist for this test module.', []

    submitted_ids = []
    canonical_answers = []
    for item in answers:
        if not isinstance(item, dict):
            return False, 'Every answer must be an object.', []

        question_id = item.get('questionID') or item.get('question_id') or item.get('id')
        if question_id in [None, '']:
            return False, 'Every answer must include questionID.', []

        try:
            question_id = int(question_id)
        except (TypeError, ValueError):
            return False, 'Invalid question ID.', []

        submitted_ids.append(question_id)
        canonical_answers.append({
            'questionID': question_id,
            'answer': item.get('answer'),
            'time_spent': item.get('time_spent', 0) or 0,
        })

    if len(submitted_ids) != len(set(submitted_ids)):
        return False, 'Duplicate question IDs are not allowed.', []

    submitted_id_set = set(submitted_ids)
    invalid_ids = submitted_id_set - expected_ids
    if invalid_ids:
        return False, 'One or more answers do not belong to this test module.', []

    missing_ids = expected_ids - submitted_id_set
    if missing_ids:
        return False, 'Submitted answers do not cover every question in this test module.', []

    return True, '', canonical_answers


def _required_modules_for_test(test_obj):
    return get_test_sequence(test_obj)


def _score_from_counts(test_mode, correct_counts):
    if test_mode == 'full':
        return calculator.get_total(
            correct_counts['english']['m1'],
            correct_counts['english']['m2'],
            correct_counts['math']['m1'],
            correct_counts['math']['m2']
        )

    if test_mode == 'ebrw_only':
        english_score, english_range = calculator.get_english(
            correct_counts['english']['m1'],
            correct_counts['english']['m2']
        )
        return {
            'total': english_score,
            'range_total': english_range,
            'sections': {
                'english': {'score': english_score, 'range': english_range},
                'math': None,
            }
        }

    if test_mode == 'math_only':
        math_score, math_range = calculator.get_math(
            correct_counts['math']['m1'],
            correct_counts['math']['m2']
        )
        return {
            'total': math_score,
            'range_total': math_range,
            'sections': {
                'english': None,
                'math': {'score': math_score, 'range': math_range},
            }
        }

    return {
        'total': 0,
        'range_total': {'lower': 0, 'upper': 0},
        'sections': {
            'english': None,
            'math': None,
        }
    }


def user_has_test_access(user, test):
    if user.is_superuser or user.is_staff or is_member(user, ['Admin', 'Tester']) or is_teacher(user):
        return True

    student_memberships = list(_approved_student_memberships(user))
    if student_memberships:
        allowed_membership_ids = [
            membership.id for membership in student_memberships
            if get_membership_section_access_map(membership).get('practice_tests')
        ]
        if not allowed_membership_ids:
            return False
        return StudentPracticeTestAccess.objects.filter(
            membership_id__in=allowed_membership_ids,
            test=test,
            has_access=True
        ).exists()

    if not test.groups.exists():
        return True

    if test.groups.filter(id__in=user.groups.all()).exists():
        return True

    return False


def _safe_answers_list(raw_answers):
    try:
        payload = json.loads(raw_answers or '{}')
    except Exception:
        return []

    answers = payload.get('answers', [])
    return answers if isinstance(answers, list) else []


def _resolve_attempt_id(user, test_obj, selected_review=None):
    if selected_review and selected_review.attempt_id:
        return selected_review.attempt_id

    latest_stage = TestStage.objects.filter(user=user, test=test_obj).order_by('-created_at').first()
    if latest_stage and latest_stage.attempt_id:
        return latest_stage.attempt_id

    latest_scored_review = TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False
    ).order_by('-created_at').first()
    if latest_scored_review and latest_scored_review.attempt_id:
        return latest_scored_review.attempt_id

    latest_module = TestModule.objects.filter(user=user, test=test_obj).order_by('-created_at').first()
    if latest_module and latest_module.attempt_id:
        return latest_module.attempt_id

    return None


def _load_latest_modules(user, test_obj, attempt_id=None):
    latest_modules = {}
    queryset = TestModule.objects.filter(user=user, test=test_obj)

    if attempt_id:
        queryset = queryset.filter(attempt_id=attempt_id)

    for module in queryset.order_by('-created_at'):
        key = f"{module.section}_{module.module}"
        if key not in latest_modules:
            latest_modules[key] = module

    if latest_modules or attempt_id:
        return latest_modules

    for module in TestModule.objects.filter(user=user, test=test_obj).order_by('-created_at'):
        key = f"{module.section}_{module.module}"
        if key not in latest_modules:
            latest_modules[key] = module

    return latest_modules


def _build_question_maps(modules_to_process):
    english_ids = set()
    math_ids = set()

    for module in modules_to_process:
        for answer in _safe_answers_list(module.answers):
            question_id = answer.get('questionID')
            if question_id in [None, '']:
                continue
            try:
                parsed_id = int(question_id)
            except (TypeError, ValueError):
                continue

            if module.section == 'english':
                english_ids.add(parsed_id)
            elif module.section == 'math':
                math_ids.add(parsed_id)

    english_map = English_Question.objects.in_bulk(english_ids) if english_ids else {}
    math_map = Math_Question.objects.in_bulk(math_ids) if math_ids else {}
    return english_map, math_map


def _latest_by_test_id(queryset, require_scored=False):
    latest = {}
    for obj in queryset:
        test_id = getattr(obj, 'test_id', None)
        if not test_id or test_id in latest:
            continue
        if require_scored and getattr(obj, 'score', None) is None:
            continue
        latest[test_id] = obj
    return latest



def _split_tests_by_user_progress(user, tests):
    """Return (active_tests, past_tests) for a user's practice-test list.

    Test.name is the primary key in this project, so all lookups must use
    test.pk/test.name instead of test.id. A test is considered past when the
    user has a scored TestReview. It remains active only when there is no
    scored review yet, or when a newer in-progress attempt exists after the
    latest scored review (retake case).
    """
    tests = list(tests)
    if not tests:
        return [], []

    test_ids = [test.pk for test in tests]

    reviews = TestReview.objects.filter(
        user=user,
        test_id__in=test_ids,
        score__isnull=False,
    ).order_by('test_id', '-created_at')
    latest_reviews = _latest_by_test_id(reviews)

    modules = TestModule.objects.filter(
        user=user,
        test_id__in=test_ids,
    ).order_by('test_id', '-created')
    stages = TestStage.objects.filter(
        user=user,
        test_id__in=test_ids,
    ).order_by('test_id', '-updated_at', '-created_at')

    latest_module_by_test = {}
    for module in modules:
        if module.test_id and module.test_id not in latest_module_by_test:
            latest_module_by_test[module.test_id] = module

    latest_stage_by_test = _latest_by_test_id(stages)

    active_tests = []
    past_tests = []

    for test in tests:
        test_key = test.pk
        review = latest_reviews.get(test_key)
        latest_module = latest_module_by_test.get(test_key)
        latest_stage = latest_stage_by_test.get(test_key)

        # Dynamic attributes are intentionally used by templates.
        test.latest_review = review
        test.latest_review_key = review.key if review and review.key else ''
        test.latest_score = review.score if review else None
        test.has_completed_attempt = bool(review)
        test.has_active_attempt = False

        has_newer_module = bool(
            latest_module and (
                not review or not review.created_at or latest_module.created > review.created_at
            )
        )
        latest_stage_at = getattr(latest_stage, 'updated_at', None) or getattr(latest_stage, 'created_at', None)
        has_newer_stage = bool(
            latest_stage and (
                not review or not review.created_at or not latest_stage_at or latest_stage_at > review.created_at
            )
        )

        if review:
            past_tests.append(test)

        if not review or has_newer_module or has_newer_stage:
            test.has_active_attempt = bool(latest_module or latest_stage)
            active_tests.append(test)

    return active_tests, past_tests


# Create your views here.

@login_required(login_url='/login/')
def practice_tests(request):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'practice_tests',
        'classroom_practice_tests',
        'You do not have access to Practice Tests.'
    )
    if classroom_response:
        return classroom_response

    user = request.user
    tests = list(Test.objects.all().distinct())
    tests = [test for test in tests if user_has_test_access(user, test)]

    def get_day_number(test):
        try:
            name = str(test.name).strip().lower()
            if name.startswith('day'):
                digits = ''.join(ch for ch in name if ch.isdigit())
                if digits:
                    return int(digits)
            return 999999
        except Exception:
            return 999999

    tests = sorted(tests, key=lambda t: (get_day_number(t), str(t.name)))

    active_tests, past_tests = _split_tests_by_user_progress(user, tests)

    purchased_packages = list(PurchasedLessonPackage.objects.filter(user=user).select_related('package'))
    if purchased_packages:
        packages = [p.package for p in purchased_packages]
        lessons = list(Lesson.objects.filter(package__in=packages))
        lesson_progress_by_id = {
            progress.lesson_id: progress
            for progress in LessonProgress.objects.filter(user=user, lesson__in=lessons)
        }

        active_lessons = []
        past_lessons = []

        for lesson in lessons:
            progress = lesson_progress_by_id.get(lesson.id)
            if progress and progress.completed:
                past_lessons.append(lesson)
            else:
                active_lessons.append(lesson)

        lessons_context = {
            'active_lessons': active_lessons,
            'past_lessons': past_lessons,
            'purchased': True,
        }
    else:
        available_packages = LessonPackage.objects.all()
        lessons_context = {
            'available_packages': available_packages,
            'purchased': False,
        }

    context = {
        'active_tests': active_tests,
        'past_tests': past_tests,
    }
    context.update(lessons_context)

    return render(request, 'sat/practice_tests.html', context)

@login_required(login_url='/login/')
def check_the_answers(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST method required.'}, status=405)

    payload = {}

    raw_body = request.body.decode('utf-8', errors='ignore').strip()
    if raw_body:
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            payload = {}

    if not payload:
        payload = request.POST.dict()

    if not payload:
        return JsonResponse({'ok': False, 'error': 'Empty request payload.'}, status=400)

    # ---------- CASE 1: full module submit ----------
    if 'answers' in payload:
        answers = payload.get('answers') or []
        section = payload.get('section')
        test_name = payload.get('test')
        module = payload.get('module')

        if not test_name or not section or not module:
            return JsonResponse({'ok': False, 'error': 'test, section, and module are required.'}, status=400)

        if not isinstance(answers, list):
            return JsonResponse({'ok': False, 'error': 'answers must be a list.'}, status=400)

        test_type = payload.get('test_type') or payload.get('testType') or 'regular'
        answers_payload = json.dumps({'answers': answers})

        if test_type == 'makeup':
            try:
                makeup_test_obj = MakeupTest.objects.get(name=test_name)
            except MakeupTest.DoesNotExist:
                return JsonResponse({'ok': False, 'error': 'Makeup test not found.'}, status=404)

            test_stage = TestStage.objects.filter(
                user=request.user,
                makeup_test=makeup_test_obj,
                test_type='makeup'
            ).order_by('-created_at').first()
            attempt_id = test_stage.attempt_id if test_stage else uuid.uuid4()

            module_obj, created = TestModule.objects.get_or_create(
                user=request.user,
                makeup_test=makeup_test_obj,
                test_type='makeup',
                section=section,
                module=module,
                attempt_id=attempt_id,
                defaults={'answers': answers_payload}
            )

            if not created:
                module_obj.answers = answers_payload
                module_obj.save(update_fields=['answers'])

            return JsonResponse({
                'ok': True,
                'saved': True,
                'section': section,
                'module': module,
                'test': test_name,
                'test_type': 'makeup',
            })

        try:
            test_obj = Test.objects.get(name=test_name)
        except Test.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Test not found.'}, status=404)

        if not user_has_test_access(request.user, test_obj):
            return JsonResponse({'ok': False, 'error': 'You do not have access to this test.'}, status=403)

        section = _normalize_test_section(section)
        module = _normalize_test_module(module)

        test_stage, _ = TestStage.objects.get_or_create(
            user=request.user,
            test=test_obj,
            defaults={'stage': 1}
        )
        current_step = get_current_test_step(test_stage)
        if current_step != (section, module):
            expected = f"{current_step[0]} / {current_step[1]}" if current_step else 'finished'
            return JsonResponse({'ok': False, 'error': f'Invalid module order. Expected {expected}.'}, status=403)

        is_valid, validation_error, canonical_answers = _validate_regular_module_answers(test_obj, section, module, answers)
        if not is_valid:
            return JsonResponse({'ok': False, 'error': validation_error}, status=400)

        answers_payload = json.dumps({'answers': canonical_answers})
        attempt_id = test_stage.attempt_id or uuid.uuid4()

        module_obj, created = TestModule.objects.get_or_create(
            user=request.user,
            test=test_obj,
            test_type='regular',
            section=section,
            module=module,
            attempt_id=attempt_id,
            defaults={'answers': answers_payload}
        )

        if not created:
            module_obj.answers = answers_payload
            module_obj.save(update_fields=['answers'])

        advance_test_stage(test_stage)

        return JsonResponse({
            'ok': True,
            'saved': True,
            'section': section,
            'module': module,
            'test': test_name,
            'test_type': 'regular',
        })

    # ---------- CASE 2: single answer check ----------
    question_id = payload.get('questionID') or payload.get('question_id') or payload.get('id')
    answer = payload.get('answer')

    if question_id in [None, '']:
        return JsonResponse({'ok': False, 'error': 'questionID is required.'}, status=400)

    try:
        question_id = int(question_id)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid questionID.'}, status=400)

    question = English_Question.objects.filter(id=question_id).first()
    section = 'english'

    if not question:
        question = Math_Question.objects.filter(id=question_id).first()
        section = 'math'

    if not question:
        return JsonResponse({'ok': False, 'error': 'Question not found.'}, status=404)

    if question.test and not user_has_test_access(request.user, question.test):
        return JsonResponse({'ok': False, 'error': 'You do not have access to this question.'}, status=403)

    if section == 'english':
        is_correct = (
            str(answer).strip().upper() == str(question.answer).strip().upper()
            if answer not in [None, ''] and question.answer not in [None, '']
            else False
        )
    else:
        is_correct = check_written(answer, question.answer)

    return JsonResponse({
        'ok': True,
        'questionID': question_id,
        'is_correct': is_correct,
        'correct_answer': question.answer,
        'your_answer': answer,
        'section': section,
    })

@login_required(login_url='login')
def punishment(request, pk):
    user = request.user
    # Remove redundant .save() call - create() already saves the object
    Punishment.objects.create(user=user, name=pk)
    return HttpResponse('You tried to cheat! Admins will be notified about this!')


@login_required(login_url='login')
def results(request, test):
    user = request.user
    test_obj = Test.objects.get(name=test)

    review_key = request.GET.get('review_key')
    attempts = list(TestReview.objects.filter(user=user, test=test_obj, score__isnull=False).order_by('-created_at'))
    selected_review = None

    if review_key:
        selected_review = next((rev for rev in attempts if rev.key == review_key), None)

    if not selected_review:
        selected_review = attempts[0] if attempts else None

    test_mode = get_test_mode(test_obj)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return HttpResponse("Questions are not found", status=404)

    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    if missing_modules:
        return HttpResponse("You need to finish all required modules")

    questions = {
        'english': {'m1': [], 'm2': []},
        'math': {'m1': [], 'm2': []}
    }

    correct_counts = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }
    time_spent_totals = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    modules_to_process = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        module_obj = latest_modules.get(key)
        if module_obj:
            modules_to_process.append(module_obj)

    english_question_map, math_question_map = _build_question_maps(modules_to_process)

    for module in modules_to_process:
        answers_list = _safe_answers_list(module.answers)

        sec = module.section
        mod = module.module

        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0) or 0)
                time_spent_totals[sec][mod] += time_spent

                question_id = int(answer['questionID'])
                if sec == 'english':
                    q_obj = english_question_map.get(question_id)
                    is_correct = bool(q_obj and answer.get('answer') == q_obj.answer)
                else:
                    q_obj = math_question_map.get(question_id)
                    raw_answer = answer.get('answer')
                    is_correct = bool(q_obj and raw_answer is not None and check_written(raw_answer, q_obj.answer))

                if not q_obj:
                    continue

                if is_correct:
                    correct_counts[sec][mod] += 1

                questions[sec][mod].append({
                    'id': answer['questionID'],
                    'status': 'correct' if is_correct else 'incorrect',
                    'answer': answer.get('answer'),
                    'number': q_obj.number,
                    'time_spent': time_spent
                })
            except Exception:
                continue

    score = _score_from_counts(test_mode, correct_counts)

    current_stage = TestStage.objects.filter(user=user, test=test_obj).order_by('-created_at').first()
    current_attempt_id = current_stage.attempt_id if current_stage else attempt_id

    if selected_review and selected_review.attempt_id:
        testreview = selected_review
    else:
        testreview = None
        if current_attempt_id:
            testreview = TestReview.objects.filter(
                user=user,
                test=test_obj,
                attempt_id=current_attempt_id
            ).order_by('-created_at').first()

        if not testreview:
            testreview = TestReview.objects.create(
                user=user,
                test=test_obj,
                attempt_id=current_attempt_id or uuid.uuid4()
            )
            testreview.update_key()
            if user.groups.filter(name='OFFLINE').exists():
                testreview.duration = timedelta(days=3)
                testreview.save(update_fields=['duration'])

    if not review_key:
        testreview.score = score['total'] if isinstance(score, dict) else 0
        testreview.save(update_fields=['score'])

    key = testreview.key
    selected_review = testreview if not review_key else selected_review

    english_total_correct = correct_counts['english']['m1'] + correct_counts['english']['m2']
    math_total_correct = correct_counts['math']['m1'] + correct_counts['math']['m2']

    english_total_time = time_spent_totals['english']['m1'] + time_spent_totals['english']['m2']
    math_total_time = time_spent_totals['math']['m1'] + time_spent_totals['math']['m2']

    total_correct = english_total_correct + math_total_correct
    total_time = english_total_time + math_total_time

    stats = {
        'total': total_correct,
        'test': test_obj.name,
        'time_spent': total_time,
        'english_time': english_total_time,
        'math_time': math_total_time,
    }

    status = {
        'english': has_english,
        'math': has_math,
        'total': True
    }

    return render(request, 'test/results.html', {
        "status": status,
        'score': score,
        'stats': stats,
        'key': key,
        'questions': questions,
        'domains': testreview.domains,
        'test_mode': test_mode,
        'has_english': has_english,
        'has_math': has_math,
        'attempts': attempts,
        'selected_review_key': selected_review.key if selected_review else '',
        'selected_review': selected_review,
        'review_key': review_key,
    })


@login_required(login_url='/login/')
def start_Practise(request, pk):
    user = request.user

    # сначала ищем тест без ограничений групп
    test = Test.objects.filter(name=pk).first()

    if not test:
        return HttpResponse(
            f"Test '{pk}' does not exist.",
            status=404
        )

    if not user_has_test_access(user, test):
        return HttpResponse(
            f"Test '{pk}' is not assigned to your account.",
            status=403
        )

    # Check if test is already completed
    completed_review = TestReview.objects.filter(
        user=user,
        test=test,
        score__isnull=False
    ).order_by('-created_at').first()
    
    if completed_review:
        return redirect('results', test=test.name)

    test_stage = TestStage.objects.filter(
        user=user,
        test=test
    )

    if test_stage.exists():
        return redirect('test', pk=test.name)

    # Check if there's an in-progress attempt by checking for incomplete modules
    has_active_attempt = TestModule.objects.filter(
        user=user,
        test=test
    ).exists()

    return render(
        request,
        'test/test_modules.html',
        {
            'test': test,
            'has_active_attempt': has_active_attempt,
        }
    )


@login_required(login_url='/login/')
def question(request, key, section, module, id):
    group, _ = Group.objects.get_or_create(name='OFFLINE')

    review = TestReview.objects.filter(key=key).select_related('user', 'test', 'makeup_test').first()
    if not review:
        return HttpResponse('This review is no longer available. A new retake may already be in progress.')

    # Owner/admin/offline check
    if request.user != review.user and not request.user.groups.filter(name='Admin').exists():
        return HttpResponseForbidden("You do not have permission to view this review.")

    if not review.is_active():
        if not (group in request.user.groups.all() or request.user.groups.filter(name='Admin').exists()):
            review_started = review.created_at.strftime('%B %d, %Y at %I:%M %p')
            review_duration = str(review.duration)
            expired_time = (review.created_at + review.duration).strftime('%B %d, %Y at %I:%M %p')

            return render(request, 'sat/review_time_over.html', {
                'test_name': review.test.name if review.test else (review.makeup_test.name if review.makeup_test else 'Unknown'),
                'review_started': review_started,
                'review_duration': review_duration,
                'expired_time': expired_time
            })

    # Review exists, but was invalidated because retake has started
    if review.score is None:
        if request.user == review.user and review.test:
            return redirect('test', pk=review.test.name)
        return HttpResponse('Review is unavailable because a retake is currently in progress.')

    module_obj = TestModule.objects.filter(
        test=review.test,
        user=review.user,
        section=section,
        module=module,
        attempt_id=review.attempt_id
    ).first()

    if not module_obj:
        if request.user == review.user and review.test:
            return redirect('test', pk=review.test.name)
        return HttpResponse('Review for this section is unavailable because a retake is currently in progress.')

    prev, answer, new = module_obj.find_answer(question_id=id)
    prev = f'/sat/question/{key}/{section}/{module}/{prev}' if prev else ''
    new = f'/sat/question/{key}/{section}/{module}/{new}' if new else ''

    if section == 'english':
        question = English_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_eng.html', {
            'question': question,
            'answered': answer,
            'prev': prev,
            'next': new,
            'test': review.test
        })

    if section == 'math':
        question = Math_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_math.html', {
            'question': question,
            'answered': answer,
            'prev': prev,
            'next': new,
            'test': review.test
        })

    return HttpResponse('Invalid section')


def clear(request, module, test, section):
    return render(request, 'clearing.html', {'module': module, 'test': test, 'section': section})


#
# Make UP tests goes here 
#

@login_required(login_url='/login/')
def start_makeup_test(request, pk):
    user = request.user
    user_groups = user.groups.all()

    try:
        makeup_test = MakeupTest.objects.filter(name=pk, groups__in=user_groups).distinct()[0]
    except Exception:
        return HttpResponse('Makeup Test Not Found or Permission Denied')

    test_stage = TestStage.objects.filter(user=user, makeup_test=makeup_test, test_type='makeup')
    if test_stage.exists():
        return redirect('makeup_test_module', pk=makeup_test.name)

    classroom = None
    approved_membership = ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved'
    ).select_related('classroom').first()

    if approved_membership and approved_membership.classroom:
        classroom = approved_membership.classroom

    return render(request, 'test/makeup_test_start.html', {
        'makeup_test': makeup_test,
        'classroom': classroom,
    })

@login_required(login_url='/login/')
def makeup_test_module(request, pk):
    user = request.user
    user_groups = user.groups.all()

    makeup_test = MakeupTest.objects.filter(name=pk, groups__in=user_groups).distinct().first()
    if not makeup_test:
        return HttpResponse('Permission Error', status=403)

    test_stage, created = TestStage.objects.get_or_create(
        user=user,
        makeup_test=makeup_test,
        test_type='makeup',
        defaults={'stage': 1}
    )

    sequence = get_makeup_test_sequence(makeup_test)
    if not sequence:
        return HttpResponse('No questions available for this module')

    if test_stage.stage < 1:
        test_stage.stage = 1
        test_stage.save(update_fields=['stage'])

    if test_stage.stage > len(sequence):
        return redirect('dashboard')

    section, module = sequence[test_stage.stage - 1]

    existing_module = TestModule.objects.filter(
        makeup_test=makeup_test,
        section=section,
        module=module,
        user=user,
        test_type='makeup',
        attempt_id=test_stage.attempt_id
    )

    if existing_module.exists():
        if test_stage.stage >= len(sequence):
            return redirect('dashboard')
        test_stage.stage += 1
        test_stage.save(update_fields=['stage'])
        return redirect('makeup_test_module', pk=makeup_test.name)

    module_name = f'module_{module[1]}'

    if section == 'english':
        questions = makeup_test.get_module_questions(section, module_name)
        if questions.exists():
            return render(request, 'test/makeup_eng.html', {
                'questions': questions,
                'module': module,
                'test': makeup_test,
                'section': section,
                'is_makeup': True
            })

    if section == 'math':
        questions = makeup_test.get_module_questions(section, module_name)
        if questions.exists():
            questions_data = []
            for q in questions:
                questions_data.append({
                    'id': q.id,
                    'passage': q.passage or '',
                    'number': q.number,
                    'question': q.question or '',
                    'a': q.get_a() if hasattr(q, 'get_a') else '',
                    'b': q.get_b() if hasattr(q, 'get_b') else '',
                    'c': q.get_c() if hasattr(q, 'get_c') else '',
                    'd': q.get_d() if hasattr(q, 'get_d') else '',
                    'type': str(q.written),
                    'graph': q.get_graph() if hasattr(q, 'get_graph') else '',
                })

            return render(request, 'test/test_math.html', {
                'questions': questions,
                'questions_data': questions_data,
                'module': module,
                'test': makeup_test,
                'section': section,
                'is_makeup': True
            })

    return HttpResponse('No questions available for this module')

@login_required(login_url='/login/')
def module_test(request, pk):

    user = request.user

    # получаем тест БЕЗ жесткой фильтрации по группам
    test = Test.objects.filter(name=pk).first()

    if not test:
        return HttpResponse("Test not found")

    if not user_has_test_access(user, test):
        return HttpResponse("Permission Error")

    # получаем последовательность модулей
    sequence = get_test_sequence(test)

    if not sequence:
        return HttpResponse("Questions are not found")

    # получаем stage
    test_stage, created = TestStage.objects.get_or_create(
        user=user,
        test=test,
        defaults={'stage': 1}
    )

    # определяем текущий шаг
    current_step = get_current_test_step(test_stage)

    if current_step is None:
        return redirect('results', test=test)

    section, module = current_step

    # проверяем существует ли уже завершённый модуль для текущей попытки
    existing_module = TestModule.objects.filter(
        test=test,
        section=section,
        module=module,
        user=user,
        attempt_id=test_stage.attempt_id
    )

    if existing_module.exists():

        finished = advance_test_stage(test_stage)

        if finished:
            return redirect('results', test=test)

        return module_test(request, pk=test.pk)

    # кастомное время для OFFLINE режима
    custom_time_seconds = None

    if user.groups.filter(name='OFFLINE').exists():

        profile, created = UserProfile.objects.get_or_create(user=user)

        if section == 'english':
            custom_time_seconds = profile.get_english_time_seconds()

        elif section == 'math':
            custom_time_seconds = profile.get_math_time_seconds()

    # ENGLISH
    if section == 'english':

        questions = English_Question.objects.filter(
            test=test,
            module=f'module_{module[1]}'
        ).order_by('number')

        if not questions.exists():

            finished = advance_test_stage(test_stage)

            if finished:
                return redirect('results', test=test)

            return module_test(request, pk=test.pk)

        return render(request, 'test/test_eng.html', {
            'questions': questions,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds
        })

    # MATH
    if section == 'math':

        questions = Math_Question.objects.filter(
            test=test,
            module=f'module_{module[1]}'
        ).order_by('number')

        if not questions.exists():

            finished = advance_test_stage(test_stage)

            if finished:
                return redirect('results', test=test)

            return module_test(request, pk=test.pk)

        questions_data = []

        for q in questions:

            questions_data.append({

                "id": q.id,
                "passage": q.passage or "",
                "number": q.number,
                "question": q.question or "",

                "a": q.get_a() if hasattr(q, "get_a") else "",
                "b": q.get_b() if hasattr(q, "get_b") else "",
                "c": q.get_c() if hasattr(q, "get_c") else "",
                "d": q.get_d() if hasattr(q, "get_d") else "",

                "type": str(q.written),

                "graph": q.get_graph() if hasattr(q, "get_graph") else "",
            })

        return render(request, 'test/test_math.html', {

            'questions': questions,
            'questions_data': questions_data,

            'module': module,
            'test': test,
            'section': section,

            'custom_time_seconds': custom_time_seconds
        })

    return HttpResponse("You dont have permission")

def rankings(request, pk):
    results = TestReview.objects.filter(test__name=pk).order_by('-score', 'user')[:50]
    return render(request, 'test/features/rankings.html', {'results': results})


@allowed_users(['Admin'])
def results_by_user(request, test, username):
    test_obj = Test.objects.get(name=test)
    user = User.objects.get(username=username)

    review_key = request.GET.get('review_key')
    attempts = list(TestReview.objects.filter(user=user, test=test_obj, score__isnull=False).order_by('-created_at'))
    selected_review = None

    if review_key:
        selected_review = next((rev for rev in attempts if rev.key == review_key), None)

    if not selected_review:
        selected_review = attempts[0] if attempts else None

    test_mode = get_test_mode(test_obj)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    questions = {
        'english': {'m1': [], 'm2': []},
        'math': {'m1': [], 'm2': []}
    }

    correct_counts = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    time_spent_totals = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    status = {
        'english': False,
        'math': False,
        'total': False
    }

    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return HttpResponse("Questions are not found", status=404)

    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    if not missing_modules:
        status['total'] = True
    if has_english and 'english_m1' not in missing_modules and 'english_m2' not in missing_modules:
        status['english'] = True
    if has_math and 'math_m1' not in missing_modules and 'math_m2' not in missing_modules:
        status['math'] = True

    if missing_modules:
        return HttpResponse('You need to finish all required modules')

    modules_to_process = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        module_obj = latest_modules.get(key)
        if module_obj:
            modules_to_process.append(module_obj)

    english_question_map, math_question_map = _build_question_maps(modules_to_process)

    for module in modules_to_process:
        answers_list = _safe_answers_list(module.answers)

        sec = module.section
        mod = module.module

        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0) or 0)
                time_spent_totals[sec][mod] += time_spent

                question_id = int(answer['questionID'])
                if sec == 'english':
                    q_obj = english_question_map.get(question_id)
                    is_correct = bool(q_obj and answer.get('answer') == q_obj.answer)
                    display_answer = answer.get('answer')
                else:
                    q_obj = math_question_map.get(question_id)
                    raw_answer = answer.get('answer')
                    is_correct = bool(q_obj and raw_answer is not None and check_written(raw_answer, q_obj.answer))
                    display_answer = raw_answer.replace('/', '-') if raw_answer else raw_answer

                if not q_obj:
                    continue

                if is_correct:
                    correct_counts[sec][mod] += 1

                questions[sec][mod].append({
                    'id': answer['questionID'],
                    'status': 'correct' if is_correct else 'incorrect',
                    'answer': display_answer,
                    'number': q_obj.number,
                    'time_spent': time_spent
                })
            except Exception:
                continue

    score = _score_from_counts(test_mode, correct_counts)

    english_total_correct = correct_counts['english']['m1'] + correct_counts['english']['m2']
    math_total_correct = correct_counts['math']['m1'] + correct_counts['math']['m2']

    english_total_time = time_spent_totals['english']['m1'] + time_spent_totals['english']['m2']
    math_total_time = time_spent_totals['math']['m1'] + time_spent_totals['math']['m2']

    total_correct = english_total_correct + math_total_correct

    stats = {
        'total': total_correct,
        'test': test_obj.name,
        'english_time': english_total_time,
        'math_time': math_total_time,
        'time_spent': english_total_time + math_total_time,
    }

    return render(request, 'test/results.html', {
        'user': user,
        'status': status,
        'score': score,
        'stats': stats,
        'key': selected_review.key if selected_review else '',
        'questions': questions,
        'test_mode': test_mode,
        'has_english': has_english,
        'has_math': has_math,
        'attempts': attempts,
        'selected_review_key': selected_review.key if selected_review else '',
        'selected_review': selected_review,
        'review_key': review_key,
        'domains': selected_review.domains if selected_review else False,
    })


def _generate_certificate_response(user, test_obj, testreview):
    test_mode = get_test_mode(test_obj)
    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return HttpResponse("No valid questions found for certificate", status=400)

    response = testreview.check_and_update_domains()
    if response is not True or not testreview.domains:
        return HttpResponse('Domains are not entered to this practise questions')

    if testreview.certificate != '':
        try:
            if testreview.certificate.startswith('certificates/'):
                from apps.sat.storages import PrivateStorage
                storage = PrivateStorage()
                return HttpResponseRedirect(storage.url(testreview.certificate))
            return FileResponse(open(testreview.certificate, 'rb'), content_type='application/pdf')
        except Exception:
            pass

    domain_names = [
        "Information and Ideas",
        "Craft and Structure",
        "Expression of Ideas",
        "Standard English Conventions",
        "Algebra",
        "Advanced Math",
        "Problem-Solving and Data Analysis",
        "Geometry and Trigonometry",
    ]
    questions = {
        'wrongs': {name: 0 for name in domain_names},
        'total': {name: 0 for name in domain_names},
    }

    latest_modules = _load_latest_modules(user, test_obj, attempt_id=testreview.attempt_id)
    modules_to_process = []
    for section, module in required_modules:
        module_obj = latest_modules.get(f"{section}_{module}")
        if not module_obj:
            return HttpResponse("Certificate cannot be generated because this attempt is incomplete.", status=400)
        modules_to_process.append(module_obj)

    english_question_map, math_question_map = _build_question_maps(modules_to_process)
    correct_counts = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0},
    }

    for module_obj in modules_to_process:
        sec = module_obj.section
        mod = module_obj.module
        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in _safe_answers_list(module_obj.answers):
            try:
                question_id = int(answer['questionID'])
                if sec == 'english':
                    db_question = english_question_map.get(question_id)
                    is_correct = bool(
                        db_question and
                        str(answer.get('answer', '')).strip().upper() == str(db_question.answer or '').strip().upper()
                    )
                else:
                    db_question = math_question_map.get(question_id)
                    raw_answer = answer.get('answer')
                    is_correct = bool(db_question and raw_answer is not None and check_written(raw_answer, db_question.answer))

                if not db_question or not db_question.domain:
                    continue

                domain_name = db_question.domain.name
                if domain_name not in questions['total']:
                    questions['total'][domain_name] = 0
                    questions['wrongs'][domain_name] = 0

                questions['total'][domain_name] += 1
                if is_correct:
                    correct_counts[sec][mod] += 1
                else:
                    questions['wrongs'][domain_name] += 1
            except Exception:
                continue

    score = _score_from_counts(test_mode, correct_counts)

    counts = [7, 7, 7, 7, 7, 7, 7, 7]
    wrongs = [questions['wrongs'].get(name, 0) for name in domain_names]
    totals = [questions['total'].get(name, 0) for name in domain_names]

    for i in range(4):
        factor = wrongs[i] // 2
        if factor >= 7:
            counts[i] = 0
            continue
        counts[i] -= factor

    for i in range(4, 8):
        counts[i] = custom_round((totals[i] - wrongs[i]) / totals[i] * 7) if totals[i] > 0 else 0

    english_section = score['sections'].get('english') or {'score': 0, 'range': {'lower': 0, 'upper': 0}}
    math_section = score['sections'].get('math') or {'score': 0, 'range': {'lower': 0, 'upper': 0}}
    range_total = score.get('range_total') or {'lower': score['total'], 'upper': score['total']}

    details = {
        "t-sc": str(score['total']),
        "t-rs": f"{range_total['lower']}-{range_total['upper']}",
        "full_name": user.username,
        "test_name": test_obj.name,
        "test_date": str(testreview.created_at)[:11],
        "r-sc": str(english_section['score']),
        "r-rs": f"{english_section['range']['lower']}-{english_section['range']['upper']}",
        "m-sc": str(math_section['score']),
        "m-rs": f"{math_section['range']['lower']}-{math_section['range']['upper']}",
    }

    output = create_certificate(details, testreview.key, BASE_DIR, counts)
    testreview.certificate = output
    testreview.save(update_fields=['certificate'])

    from apps.sat.storages import PrivateStorage
    storage = PrivateStorage()
    return HttpResponseRedirect(storage.url(testreview.certificate))


@login_required(login_url='login')
def certificate(request, test, key=None):
    test_obj = get_object_or_404(Test, pk=test)
    review_key = key or request.GET.get('review_key')
    if not review_key:
        return HttpResponse("Certificate must be requested with a review key.", status=400)

    testreview = TestReview.objects.filter(
        user=request.user,
        test=test_obj,
        key=review_key,
        score__isnull=False,
    ).first()

    if not testreview:
        return HttpResponse("Invalid TEST review contact tech@sat800makon.uz", status=404)

    return _generate_certificate_response(request.user, test_obj, testreview)


@allowed_users(['Admin'])
def certificate_by_user(request, test, username, key=None):
    test_obj = get_object_or_404(Test, pk=test)
    user = get_object_or_404(User, username=username)
    review_key = key or request.GET.get('review_key')
    if not review_key:
        return HttpResponse("Certificate must be requested with a review key.", status=400)

    testreview = TestReview.objects.filter(
        user=user,
        test=test_obj,
        key=review_key,
        score__isnull=False,
    ).first()

    if not testreview:
        return HttpResponse("Invalid TEST review contact tech@sat800makon.uz", status=404)

    return _generate_certificate_response(user, test_obj, testreview)


@login_required(login_url='/login/')
def enter_secret_code(request):
    """
    Handles the secret code entry form submission.
    Validates a 6-digit code entered across six input fields, adds the user to the associated group,
    and redirects accordingly.
    """
    if request.method == "POST":
        # Collect the 6 digits from the individual input fields
        code_digits = [
            request.POST.get(f'code_{i}', '').strip() for i in range(1, 7)
        ]

        code = ''.join(code_digits).upper()

        # Validate the code
        if not code or len(code) != 6 or not code.isalnum():
            messages.error(request, "Please enter a valid 6-character code using letters or numbers only.")
        else:
            try:
                secret_code = SecretCode.objects.get(code=code)
                user = request.user
                
                # Add user to the specified group if not already a member
                if secret_code.group not in user.groups.all():
                    user.groups.add(secret_code.group)
                    user.save()
                    messages.success(request, f"You have been added to the '{secret_code.group.name}' group!")
                else:
                    messages.info(request, "You are already in this group.")

                # Redirect based on whether a test or makeup_test is linked
                if secret_code.test:
                    return redirect('practise', pk=secret_code.test.name)  # Redirect to start_test if test exists
                elif secret_code.makeup_test:
                    return redirect('start_makeup_test', pk=secret_code.makeup_test.name)  # Existing makeup_test redirection
                return redirect('dashboard')  # Default redirection if no test or makeup_test
            except SecretCode.DoesNotExist:
                ap_event = None
                if APExamEvent is not None:
                    ap_event = APExamEvent.objects.filter(
                        access_code__iexact=code,
                        is_public=True,
                        status='live',
                    ).order_by('-updated_at').first()
                if ap_event:
                    if not ap_event.is_live_now:
                        messages.error(request, "This AP mock exam is not live now.")
                        return redirect('enter_secret_code')
                    request.session[f"ap_event_{ap_event.pk}_secret_ok"] = True
                    request.session.modified = True
                    return redirect('apclasses:start_event', slug=ap_event.slug)
                messages.error(request, "Invalid secret code. Please try again.")

    return render(request, 'sat/enter_code.html', {})


@login_required(login_url='login')
@require_POST
def restart_section(request, pk, section):
    close_old_connections()

    user = request.user

    test = Test.objects.filter(name=pk).first()

    if not test:
        return HttpResponse(f"Test '{pk}' not found")

    if not user_has_test_access(user, test):
        return HttpResponse(
            f"Test '{pk}' is not assigned to your account.",
            status=403
        )

    stage, _ = TestStage.objects.get_or_create(
        user=user,
        test=test,
        defaults={"stage": 1}
    )

    # Try to restart the section
    response = stage.resolve_section(section)

    if response:
        # Restart successful
        return render(request, 'sat/restart_success.html', {
            'test_name': pk,
            'section': section
        })
    else:
        # Retake limit exceeded
        user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'
        
        return render(request, 'sat/retake_limit_exceeded.html', {
            'test_name': pk,
            'section': section,
            'retakes_used': stage.retake_count,
            'max_retakes': stage.get_max_retakes(),
            'user_group': user_group
        })


@login_required(login_url='/login/')
def vocabulary(request):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'vocabulary',
        'classroom_vocabulary',
        'You do not have access to Vocabulary.'
    )
    if classroom_response:
        return classroom_response

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary.html', {
        'units': units
    })


ADMISSIONS_SECTIONS = {
    "university_guide": {
        "title": "University Guide",
        "description": "Basic guidance for choosing universities and programs.",
        "items": [
            {
                "title": "How to Compare Universities",
                "content": [
                    "Check tuition and total cost, not just headline tuition.",
                    "Look at major strength, not just university ranking.",
                    "Check scholarship availability for international students.",
                    "Compare location, campus size, and internship access.",
                    "Look at graduation outcomes and career support.",
                ]
            },
            {
                "title": "What to Research",
                "content": [
                    "Application deadlines",
                    "Required English test scores",
                    "SAT/optional policy",
                    "Financial aid for internationals",
                    "Major-specific requirements",
                ]
            },
        ]
    },
    "application_help": {
        "title": "Application Help",
        "description": "Step-by-step help for preparing your college applications.",
        "items": [
            {
                "title": "Core Application Checklist",
                "content": [
                    "Create university account/Common App account",
                    "Prepare passport and personal details",
                    "Add school and academic information",
                    "Prepare IELTS/TOEFL scores",
                    "Prepare SAT scores if needed",
                    "Write personal essay",
                    "Request recommendation letters",
                    "Upload transcripts",
                ]
            },
            {
                "title": "Essay Advice",
                "content": [
                    "Be specific, not generic",
                    "Show personal growth",
                    "Avoid fake drama",
                    "Use real examples",
                    "Keep structure clear",
                ]
            },
        ]
    },
    "scholarships": {
        "title": "Scholarships",
        "description": "Basic overview of scholarship planning.",
        "items": [
            {
                "title": "Common Scholarship Types",
                "content": [
                    "Merit scholarships",
                    "Need-based aid",
                    "International student grants",
                    "Department scholarships",
                    "External private scholarships",
                ]
            },
            {
                "title": "What Usually Helps",
                "content": [
                    "Strong GPA",
                    "High English proficiency scores",
                    "Strong SAT if required",
                    "Good essay",
                    "Clear extracurricular profile",
                    "Early application",
                ]
            },
        ]
    },
}


@login_required(login_url='/login/')
def vocabulary_section(request, slug):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'vocabulary',
        'classroom_vocabulary',
        'You do not have access to Vocabulary.'
    )
    if classroom_response:
        return classroom_response

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    if slug == 'word_lists':
        return render(request, 'sat/vocabulary_word_lists.html', {
            'units': units
        })

    if slug == 'flashcards':
        return render(request, 'sat/vocabulary_flashcards.html', {
            'units': units
        })

    raise Http404("Vocabulary section not found")


@login_required(login_url='/login/')
def admissions(request):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'admissions',
        'classroom_admissions',
        'You do not have access to Admissions.'
    )
    if classroom_response:
        return classroom_response

    return render(request, 'sat/admissions.html', {
        'sections': ADMISSIONS_SECTIONS
    })


@login_required(login_url='/login/')
def admissions_section(request, slug):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'admissions',
        'classroom_admissions',
        'You do not have access to Admissions.'
    )
    if classroom_response:
        return classroom_response

    section = ADMISSIONS_SECTIONS.get(slug)
    if not section:
        raise Http404("Admissions section not found")

    return render(request, 'sat/admissions_section.html', {
        'slug': slug,
        'section': section,
    })

@login_required(login_url='/login/')
def vocabulary_practice_quiz(request):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'vocabulary',
        'classroom_vocabulary',
        'You do not have access to Vocabulary.'
    )
    if classroom_response:
        return classroom_response

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary_practice_quiz.html', {
        'units': units
    })

@login_required(login_url='/login/')
def vocabulary_practice_quiz_start(request):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'vocabulary',
        'classroom_vocabulary',
        'You do not have access to Vocabulary.'
    )
    if classroom_response:
        return classroom_response

    if request.method != 'POST':
        return redirect('vocabulary_practice_quiz')

    selected_ids = request.POST.getlist('units')
    selected_ids = [int(x) for x in selected_ids if x.isdigit()]
    requested_count = request.POST.get('question_count')

    if not selected_ids:
        messages.error(request, "Select at least one unit.")
        return redirect('vocabulary_practice_quiz')

    try:
        requested_count = int(requested_count)
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid number of questions.")
        return redirect('vocabulary_practice_quiz')

    selected_units = VocabularyUnit.objects.filter(
        id__in=selected_ids,
        is_active=True
    ).prefetch_related('words')

    selected_words = []
    for unit in selected_units:
        for word in unit.words.filter(is_active=True):
            selected_words.append(word)

    if len(selected_words) < 4:
        messages.error(request, "You need at least 4 words in the selected units to generate a quiz.")
        return redirect('vocabulary_practice_quiz')

    max_available = len(selected_words)

    if requested_count < 1:
        messages.error(request, "Question count must be at least 1.")
        return redirect('vocabulary_practice_quiz')

    if requested_count > max_available:
        messages.error(request, f"You selected {requested_count} questions, but only {max_available} words are available.")
        return redirect('vocabulary_practice_quiz')

    random.shuffle(selected_words)
    test_words = selected_words[:requested_count]

    all_meanings_pool = [w.meaning for w in selected_words]

    questions = []
    for word_obj in test_words:
        correct_answer = word_obj.meaning

        wrong_answers = [m for m in all_meanings_pool if m != correct_answer]
        wrong_answers = list(set(wrong_answers))
        random.shuffle(wrong_answers)
        wrong_answers = wrong_answers[:3]

        if len(wrong_answers) < 3:
            continue

        choices = [correct_answer] + wrong_answers
        random.shuffle(choices)

        questions.append({
            'unit': word_obj.unit.title,
            'question': f"What is the meaning of '{word_obj.word}'?",
            'choices': choices,
            'answer': correct_answer,
            'word': word_obj.word,
        })

    if not questions:
        messages.error(request, "Could not generate quiz questions from selected words.")
        return redirect('vocabulary_practice_quiz')

    request.session['vocab_quiz_questions'] = questions
    request.session['vocab_quiz_units'] = [u.title for u in selected_units]

    return render(request, 'sat/vocabulary_practice_quiz_test.html', {
        'questions': questions,
        'selected_units': selected_units,
        'requested_count': len(questions),
    })


@login_required(login_url='/login/')
def vocabulary_practice_quiz_result(request):
    classroom_response = _redirect_or_deny_classroom_section(
        request,
        'vocabulary',
        'classroom_vocabulary',
        'You do not have access to Vocabulary.'
    )
    if classroom_response:
        return classroom_response

    if request.method != 'POST':
        return redirect('vocabulary_practice_quiz')

    questions = request.session.get('vocab_quiz_questions', [])
    score = 0
    total_questions = len(questions)
    results = []

    for i, q in enumerate(questions):
        user_answer = request.POST.get(f'question_{i}')
        is_correct = user_answer == q['answer']

        if is_correct:
            score += 1

        results.append({
            'unit': q['unit'],
            'question': q['question'],
            'correct_answer': q['answer'],
            'user_answer': user_answer,
            'is_correct': is_correct,
            'word': q.get('word', ''),
        })

    percentage = (score / total_questions * 100) if total_questions > 0 else 0

    # Clear session data
    request.session.pop('vocab_quiz_questions', None)
    request.session.pop('vocab_quiz_units', None)
    request.session.pop('vocab_quiz_classroom_id', None)

    return render(request, 'sat/vocabulary_practice_quiz_result.html', {
        'results': results,
        'score': score,
        'total': total_questions,
        'total_questions': total_questions,
        'percentage': percentage,
        'selected_units': request.session.get('vocab_quiz_units', []),
    })

@login_required(login_url='/login/')
def vocabulary_flashcards(request):

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary_flashcards.html', {
        'units': units
    })

def is_teacher(user):
    return (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name__iexact='teacher').exists()
    )


def generate_6_digit_code():
    return f"{random.randint(0, 999999):06d}"


def generate_unique_classroom_code():
    while True:
        code = generate_6_digit_code()
        if not ClassroomJoinCode.objects.filter(code=code, is_active=True).exists():
            return code

@login_required(login_url='/login/')
def teacher_classroom_list(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can access classroom management.")

    classrooms = Classroom.objects.filter(teacher=request.user).order_by('-created_at')

    return render(request, 'sat/teacher_classroom_list.html', {
        'classrooms': classrooms,
    })

@login_required(login_url='/login/')
def update_student_practice_test_access(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership,
        classroom=classroom,
        user_id=user_id,
        role='student',
        status='approved'
    )

    tests = Test.objects.all().distinct().order_by('name')

    if request.method == 'POST':
        access_mode = request.POST.get('access_mode', 'all')
        selected_test_names = request.POST.getlist('tests')

        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            messages.error(request, "First enable Practice Tests section access for this student.")
            return redirect(
                'update_student_practice_test_access',
                classroom_id=classroom.id,
                user_id=user_id
            )

        StudentPracticeTestAccess.objects.filter(membership=membership).delete()

        if access_mode == 'all':
            selected_tests = tests
        else:
            selected_tests = Test.objects.filter(pk__in=selected_test_names).distinct()

        for test in selected_tests:
            StudentPracticeTestAccess.objects.update_or_create(
                membership=membership,
                test=test,
                defaults={'has_access': True}
            )

        messages.success(request, "Student practice test access updated successfully.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    existing_items = StudentPracticeTestAccess.objects.filter(
        membership=membership,
        has_access=True
    )

    selected_test_ids = set(existing_items.values_list('test_id', flat=True))
    access_mode = 'selected' if existing_items.exists() else 'all'

    return render(request, 'sat/update_student_practice_test_access.html', {
        'classroom': classroom,
        'membership': membership,
        'tests': tests,
        'selected_test_ids': selected_test_ids,
        'access_mode': access_mode,
    })

@login_required(login_url='/login/')
def create_classroom(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can create classrooms.")

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Classroom name is required.")
            return redirect('create_classroom')

        classroom = Classroom.objects.create(
            teacher=request.user,
            name=name,
            description=description,
            is_active=True,
        )

        # create teacher membership automatically
        ClassroomMembership.objects.get_or_create(
            classroom=classroom,
            user=request.user,
            defaults={
                'role': 'teacher',
                'status': 'approved',
                'approved_at': timezone.now(),
            }
        )

        messages.success(request, f'Classroom "{classroom.name}" created successfully.')
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    return render(request, 'sat/create_classroom.html')

@login_required(login_url='/login/')
def teacher_classroom_dashboard(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    students = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student'
    ).select_related('user').order_by('-requested_at')

    join_code = getattr(classroom, 'join_code', None)

    return render(request, 'sat/teacher_classroom_dashboard.html', {
        'classroom': classroom,
        'students': students,
        'join_code': join_code,
    })

@login_required(login_url='/login/')
def generate_classroom_join_code(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    if request.method != 'POST':
        messages.error(request, "Generating a join code requires POST.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    old_code = ClassroomJoinCode.objects.filter(classroom=classroom).first()
    if old_code:
        old_code.is_active = False
        old_code.save()

    new_code = generate_unique_classroom_code()

    ClassroomJoinCode.objects.update_or_create(
        classroom=classroom,
        defaults={
            'code': new_code,
            'expires_at': timezone.now() + timedelta(hours=12),
            'is_active': True,
        }
    )

    messages.success(request, f"New join code generated for {classroom.name}.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def get_user_approved_student_membership(user):
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved'
    ).select_related('classroom').first()


def get_user_pending_student_membership(user):
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='pending'
    ).select_related('classroom').first()


def is_student(user):
    return user.groups.filter(name='student').exists() or not is_teacher(user)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_join_code_rate_limited(request):
    ip = get_client_ip(request)
    key = f"classroom_join_attempts:{ip}"
    attempts = cache.get(key, 0)
    return attempts >= 5


def register_join_code_attempt(request):
    ip = get_client_ip(request)
    key = f"classroom_join_attempts:{ip}"
    attempts = cache.get(key, 0)
    cache.set(key, attempts + 1, timeout=600)  # 10 minutes

@login_required(login_url='/login/')
def classroom_entry(request):
    if is_teacher(request.user):
        return redirect('teacher_classroom_list')

    approved_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='approved'
    ).select_related('classroom').first()

    if approved_membership:
        if approved_membership.classroom and approved_membership.classroom.is_active:
            return redirect('student_classroom_home', classroom_id=approved_membership.classroom.id)

    pending_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='pending'
    ).select_related('classroom').first()

    rejected_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='rejected'
    ).select_related('classroom').order_by('-requested_at').first()

    return render(request, 'sat/classroom_join.html', {
        'pending_membership': pending_membership,
        'rejected_membership': rejected_membership,
    })

@login_required(login_url='/login/')
def submit_classroom_join_request(request):
    if request.method != 'POST':
        return redirect('sat_menu')

    if is_teacher(request.user):
        return HttpResponseForbidden("Teachers cannot submit classroom join requests.")

    approved_membership = get_user_approved_student_membership(request.user)
    if approved_membership:
        messages.error(request, "You are already enrolled in a classroom.")
        return redirect('student_classroom_home', classroom_id=approved_membership.classroom.id)

    existing_pending = get_user_pending_student_membership(request.user)
    if existing_pending:
        messages.info(request, "You already have a pending classroom request.")
        return redirect('sat_menu')

    if is_join_code_rate_limited(request):
        messages.error(request, "Too many code attempts. Please wait and try again later.")
        return redirect('sat_menu')

    code = request.POST.get('join_code', '').strip()

    if not code.isdigit() or len(code) != 6:
        register_join_code_attempt(request)
        messages.error(request, "Code must contain exactly 6 digits.")
        return redirect('sat_menu')

    join_code = ClassroomJoinCode.objects.filter(
        code=code,
        is_active=True
    ).select_related('classroom').first()

    if not join_code or not join_code.is_valid():
        register_join_code_attempt(request)
        messages.error(request, "Invalid or expired classroom code.")
        return redirect('sat_menu')

    membership, created = ClassroomMembership.objects.get_or_create(
        classroom=join_code.classroom,
        user=request.user,
        defaults={
            'role': 'student',
            'status': 'pending',
        }
    )

    if not created:
        if membership.status == 'approved':
            messages.error(request, "You are already enrolled in this classroom.")
        elif membership.status == 'pending':
            messages.info(request, "Your request is already pending.")
        elif membership.status == 'rejected':
            membership.status = 'pending'
            membership.requested_at = timezone.now()
            membership.approved_at = None
            membership.save()
            messages.success(request, "Your join request has been submitted again.")
        return redirect('sat_menu')

    messages.success(request, f'Join request sent to classroom "{join_code.classroom.name}".')
    return redirect('sat_menu')

@login_required(login_url='/login/')
def classroom_join_status(request):
    approved_membership = get_user_approved_student_membership(request.user)
    if approved_membership:
        return redirect('student_classroom_home', classroom_id=approved_membership.classroom.id)

    pending_membership = get_user_pending_student_membership(request.user)

    rejected_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='rejected'
    ).select_related('classroom').order_by('-requested_at').first()

    return render(request, 'sat/classroom_join_status.html', {
        'pending_membership': pending_membership,
        'rejected_membership': rejected_membership,
    })

@login_required(login_url='/login/')
def classroom_join_requests(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    requests_qs = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student',
        status='pending'
    ).select_related('user').order_by('-requested_at')

    return render(request, 'sat/teacher_classroom_dashboard.html', {
        'classroom': classroom,
        'students': ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student'
        ).select_related('user').order_by('-requested_at'),
        'join_code': getattr(classroom, 'join_code', None),
        'pending_requests': requests_qs,
    })

@login_required(login_url='/login/')
def approve_join_request(request, classroom_id, membership_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    if request.method != 'POST':
        messages.error(request, "Approving join requests requires POST.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    membership = get_object_or_404(
        ClassroomMembership,
        id=membership_id,
        classroom=classroom,
        role='student'
    )

    existing_approved = ClassroomMembership.objects.filter(
        user=membership.user,
        role='student',
        status='approved'
    ).exclude(id=membership.id).first()

    if existing_approved:
        messages.error(request, "This student already belongs to another approved classroom.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    membership.status = 'approved'
    membership.approved_at = timezone.now()
    membership.save()

    for section in ['practice_tests', 'vocabulary', 'admissions']:
        StudentSectionAccess.objects.get_or_create(
            membership=membership,
            section=section,
            defaults={'has_access': False}
        )

    messages.success(request, f"{membership.user.username} has been approved.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

@login_required(login_url='/login/')
def reject_join_request(request, classroom_id, membership_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    if request.method != 'POST':
        messages.error(request, "Rejecting join requests requires POST.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    membership = get_object_or_404(
        ClassroomMembership,
        id=membership_id,
        classroom=classroom,
        role='student'
    )

    membership.status = 'rejected'
    membership.approved_at = None
    membership.save()

    messages.info(request, f"{membership.user.username}'s request was rejected.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def classroom_access_denied(request, classroom=None, message="You do not have access to this classroom."):
    return render(request, 'sat/classroom_access_denied.html', {
        'classroom': classroom,
        'message': message,
    }, status=403)

@login_required(login_url='/login/')
def student_classroom_home(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role in ['teacher', 'admin']:
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    if role != 'student':
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if not classroom.is_active:
        messages.error(request, "This classroom is no longer active.")
        return redirect('sat_menu')

    access_map = get_membership_section_access_map(membership)

    return render(request, 'sat/student_classroom_home.html', {
        'classroom': classroom,
        'membership': membership,
        'access_map': access_map,
    })

def get_membership_section_access_map(membership):
    result = {
        'practice_tests': False,
        'vocabulary': False,
        'admissions': False,
    }

    for item in membership.section_access.all():
        result[item.section] = item.has_access

    return result

@login_required(login_url='/login/')
def update_student_section_access(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = get_object_or_404(
        ClassroomMembership.objects.select_related('user', 'classroom'),
        classroom=classroom,
        user_id=user_id,
        role='student',
        status='approved'
    )

    if request.method == 'POST':
        selected_sections = request.POST.getlist('sections')

        all_sections = ['practice_tests', 'vocabulary', 'admissions']

        for section in all_sections:
            access_obj, _ = StudentSectionAccess.objects.get_or_create(
                membership=membership,
                section=section,
                defaults={'has_access': False}
            )
            access_obj.has_access = section in selected_sections
            access_obj.save()

        messages.success(request, f"Access updated for {membership.user.username}.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    access_map = get_membership_section_access_map(membership)

    return render(request, 'sat/update_student_section_access.html', {
        'classroom': classroom,
        'membership': membership,
        'access_map': access_map,
    })

@login_required(login_url='/login/')
def update_classroom_section_access(request, classroom_id):
    """Set section access for ALL approved students in the classroom at once."""
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    memberships = list(
        ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student',
            status='approved'
        ).select_related('user').prefetch_related('section_access')
    )

    all_sections = ['practice_tests', 'vocabulary', 'admissions']

    if request.method == 'POST':
        selected_sections = request.POST.getlist('sections')
        for membership in memberships:
            for section in all_sections:
                access_obj, _ = StudentSectionAccess.objects.get_or_create(
                    membership=membership,
                    section=section,
                    defaults={'has_access': False}
                )
                access_obj.has_access = section in selected_sections
                access_obj.save()
        messages.success(request, f"Section access updated for all {len(memberships)} students.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    # Pre-populate: a section shows as checked if more than half of students have it
    section_counts = {s: 0 for s in all_sections}
    for membership in memberships:
        amap = get_membership_section_access_map(membership)
        for section in all_sections:
            if amap.get(section):
                section_counts[section] += 1
    total = len(memberships)
    majority_access = {
        s: (section_counts[s] > total / 2) for s in all_sections
    } if total else {s: False for s in all_sections}

    return render(request, 'sat/update_classroom_section_access.html', {
        'classroom': classroom,
        'student_count': total,
        'majority_access': majority_access,
        'section_counts': section_counts,
    })


@login_required(login_url='/login/')
def classroom_vocabulary_section(request, classroom_id, slug):
    """Classroom-aware vocabulary sub-section (word_lists / flashcards)."""
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    if slug == 'word_lists':
        return render(request, 'sat/vocabulary_word_lists.html', {
            'units': units,
            'classroom': classroom,
        })

    if slug == 'flashcards':
        return render(request, 'sat/vocabulary_flashcards.html', {
            'units': units,
            'classroom': classroom,
        })

    if slug == 'practice-quiz':
        return render(request, 'sat/vocabulary_practice_quiz.html', {
            'units': units,
            'classroom': classroom,
        })

    raise Http404("Vocabulary section not found")


@login_required(login_url='/login/')
def classroom_vocabulary_practice_quiz_start(request, classroom_id):
    """Classroom-aware vocabulary practice quiz start."""
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    if request.method != 'POST':
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    selected_ids = request.POST.getlist('units')
    selected_ids = [int(x) for x in selected_ids if x.isdigit()]
    requested_count = request.POST.get('question_count')

    if not selected_ids:
        messages.error(request, "Select at least one unit.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    try:
        requested_count = int(requested_count)
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid number of questions.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    selected_units = VocabularyUnit.objects.filter(
        id__in=selected_ids,
        is_active=True
    ).prefetch_related('words')

    selected_words = []
    for unit in selected_units:
        for word in unit.words.filter(is_active=True):
            selected_words.append(word)

    if len(selected_words) < 4:
        messages.error(request, "You need at least 4 words in the selected units to generate a quiz.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    max_available = len(selected_words)

    if requested_count < 1:
        messages.error(request, "Question count must be at least 1.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    if requested_count > max_available:
        messages.error(request, f"You selected {requested_count} questions, but only {max_available} words are available.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    random.shuffle(selected_words)
    test_words = selected_words[:requested_count]

    all_meanings_pool = [w.meaning for w in selected_words]

    questions = []
    for word_obj in test_words:
        correct_answer = word_obj.meaning

        wrong_answers = [m for m in all_meanings_pool if m != correct_answer]
        wrong_answers = list(set(wrong_answers))
        random.shuffle(wrong_answers)
        wrong_answers = wrong_answers[:3]

        if len(wrong_answers) < 3:
            continue

        choices = [correct_answer] + wrong_answers
        random.shuffle(choices)

        questions.append({
            'unit': word_obj.unit.title,
            'question': f"What is the meaning of '{word_obj.word}'?",
            'choices': choices,
            'answer': correct_answer,
            'word': word_obj.word,
        })

    if not questions:
        messages.error(request, "Could not generate quiz questions from selected words.")
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    request.session['vocab_quiz_questions'] = questions
    request.session['vocab_quiz_units'] = [u.title for u in selected_units]
    request.session['vocab_quiz_classroom_id'] = classroom_id

    return render(request, 'sat/vocabulary_practice_quiz_test.html', {
        'questions': questions,
        'selected_units': selected_units,
        'requested_count': len(questions),
        'classroom': classroom,
    })


@login_required(login_url='/login/')
def classroom_vocabulary_practice_quiz_result(request, classroom_id):
    """Classroom-aware vocabulary practice quiz result."""
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    if request.method != 'POST':
        return redirect('classroom_vocabulary_section', classroom_id=classroom_id, slug='practice-quiz')

    questions = request.session.get('vocab_quiz_questions', [])
    score = 0
    total_questions = len(questions)
    results = []

    for i, question in enumerate(questions):
        user_answer = request.POST.get(f'question_{i}')
        is_correct = user_answer == question['answer']
        if is_correct:
            score += 1

        results.append({
            'question': question['question'],
            'user_answer': user_answer,
            'correct_answer': question['answer'],
            'is_correct': is_correct,
            'unit': question['unit'],
            'word': question['word'],
        })

    percentage = (score / total_questions * 100) if total_questions > 0 else 0

    # Clear session data
    request.session.pop('vocab_quiz_questions', None)
    request.session.pop('vocab_quiz_units', None)
    request.session.pop('vocab_quiz_classroom_id', None)

    return render(request, 'sat/vocabulary_practice_quiz_result.html', {
        'results': results,
        'score': score,
        'total': total_questions,
        'total_questions': total_questions,
        'percentage': percentage,
        'selected_units': request.session.get('vocab_quiz_units', []),
        'classroom': classroom,
    })


@login_required(login_url='/login/')
def remove_student_from_classroom(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    if request.method != 'POST':
        messages.error(request, "Removing a student requires POST.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    membership = get_object_or_404(
        ClassroomMembership,
        classroom=classroom,
        user_id=user_id,
        role='student'
    )

    membership.delete()
    messages.success(request, "Student removed from classroom.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

@login_required(login_url='/login/')
def classroom_practice_tests(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role in ['teacher', 'admin']:
        tests = Test.objects.all().distinct().order_by('name')
    elif role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Practice Tests."
            )

        tests = get_student_allowed_practice_tests_queryset(membership)
    else:
        tests = Test.objects.none()

    def get_day_number(test):
        try:
            name = str(test.name).strip().lower()
            if name.startswith('day'):
                digits = ''.join(ch for ch in name if ch.isdigit())
                if digits:
                    return int(digits)
            return 999999
        except Exception:
            return 999999

    tests = sorted(tests, key=lambda t: (get_day_number(t), str(t.name)))

    active_tests, past_tests = _split_tests_by_user_progress(request.user, tests)

    context = {
        'active_tests': active_tests,
        'past_tests': past_tests,
        'classroom': classroom,
        'is_teacher_view': role in ['teacher', 'admin'],
        'purchased': True,
        'active_lessons': [],
        'past_lessons': [],
        'role': role,
        'membership': membership,
        'user': request.user,
    }
    return render(request, 'sat/practice_tests.html', context)


@login_required(login_url='/login/')
def classroom_vocabulary(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Vocabulary."
            )

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary.html', {
        'units': units,
        'classroom': classroom,
    })


@login_required(login_url='/login/')
def classroom_admissions(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('admissions'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Admissions."
            )

    return render(request, 'sat/admissions.html', {
        'sections': ADMISSIONS_SECTIONS,
        'classroom': classroom,
        'role': role,
        'membership': membership,
    })


@login_required(login_url='/login/')
def classroom_admissions_section(request, classroom_id, slug):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('admissions'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Admissions."
            )

    section = ADMISSIONS_SECTIONS.get(slug)
    if not section:
        raise Http404("Admissions section not found")

    return render(request, 'sat/admissions_section.html', {
        'slug': slug,
        'section': section,
        'classroom': classroom,
        'role': role,
        'membership': membership,
    })

def _can_manage_classroom_progress(user, classroom):
    return classroom.teacher_id == user.id or user.is_superuser


def _get_classroom_student_membership_or_404(classroom, student_id):
    return get_object_or_404(
        ClassroomMembership.objects.select_related('user', 'classroom').prefetch_related('section_access'),
        classroom=classroom,
        user_id=student_id,
        role='student',
        status='approved'
    )


def _sort_tests_for_progress(tests):
    def key_fn(test):
        name = str(test.name).strip().lower()
        if name.startswith('day'):
            digits = ''.join(ch for ch in name if ch.isdigit())
            if digits:
                return (0, int(digits), str(test.name).lower())
        return (1, 999999, str(test.name).lower())

    return sorted(tests, key=key_fn)


def _get_membership_allowed_tests(membership):
    explicit_access = list(
        StudentPracticeTestAccess.objects.filter(
            membership=membership,
            has_access=True
        ).select_related('test')
    )

    if explicit_access:
        tests = [item.test for item in explicit_access]
    else:
        tests = list(Test.objects.all().distinct())

    return _sort_tests_for_progress(tests)


def _build_test_progress_rows(student, tests):
    rows = []
    tests = list(tests)

    if not tests:
        return rows

    test_ids = [test.pk for test in tests]

    modules = TestModule.objects.filter(user=student, test_id__in=test_ids).select_related('test').order_by('test_id', '-created_at')
    reviews = TestReview.objects.filter(user=student, test_id__in=test_ids).select_related('test').order_by('test_id', '-created_at')
    stages = TestStage.objects.filter(user=student, test_id__in=test_ids).select_related('test').order_by('test_id', '-created_at')

    latest_review_by_test = _latest_by_test_id(reviews)
    latest_stage_by_test = _latest_by_test_id(stages)

    latest_module_by_test = {}
    latest_by_slot_by_test = defaultdict(dict)

    for module in modules:
        test_id = module.test_id
        if test_id not in latest_module_by_test:
            latest_module_by_test[test_id] = module

        slot = f"{module.section}_{module.module}"
        if slot not in latest_by_slot_by_test[test_id]:
            latest_by_slot_by_test[test_id][slot] = module

    for test in tests:
        review = latest_review_by_test.get(test.pk)
        stage = latest_stage_by_test.get(test.pk)
        latest_module = latest_module_by_test.get(test.pk)
        latest_by_slot = latest_by_slot_by_test.get(test.pk, {})

        answered_questions = 0
        for module in latest_by_slot.values():
            answered_questions += len(_safe_answers_list(module.answers))

        if review and review.score is not None:
            status = 'completed'
        elif latest_module or stage:
            status = 'in_progress'
        else:
            status = 'not_started'

        rows.append({
            'test': test,
            'status': status,
            'score': review.score if review and review.score is not None else None,
            'review_key': review.key if review and review.score is not None else '',
            'can_open_review': bool(review and review.key and review.score is not None),
            'last_activity_at': latest_module.created_at if latest_module else (review.created_at if review else None),
            'answered_questions': answered_questions,
            'has_stage': bool(stage),
            'stage_value': stage.stage if stage else None,
        })

    return rows


def _build_test_results_context_for_user(test_obj, user):
    test_mode = get_test_mode(test_obj)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    questions = {
        'english': {'m1': [], 'm2': []},
        'math': {'m1': [], 'm2': []}
    }

    correct_counts = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    time_spent_totals = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0}
    }

    status = {
        'english': False,
        'math': False,
        'total': False
    }

    required_modules = _required_modules_for_test(test_obj)

    attempt_id = _resolve_attempt_id(user, test_obj)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    if not missing_modules:
        status['total'] = True
    if has_english and 'english_m1' not in missing_modules and 'english_m2' not in missing_modules:
        status['english'] = True
    if has_math and 'math_m1' not in missing_modules and 'math_m2' not in missing_modules:
        status['math'] = True

    if missing_modules:
        return {
            'is_complete': False,
            'missing_modules': missing_modules,
            'status': status,
            'test_mode': test_mode,
            'has_english': has_english,
            'has_math': has_math,
            'questions': questions,
        }

    modules_to_process = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        module_obj = latest_modules.get(key)
        if module_obj:
            modules_to_process.append(module_obj)

    english_question_map, math_question_map = _build_question_maps(modules_to_process)

    for module in modules_to_process:
        answers_list = _safe_answers_list(module.answers)

        sec = module.section
        mod = module.module

        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0) or 0)
                time_spent_totals[sec][mod] += time_spent

                question_id = int(answer['questionID'])
                if sec == 'english':
                    q_obj = english_question_map.get(question_id)
                    is_correct = bool(q_obj and answer.get('answer') == q_obj.answer)
                    display_answer = answer.get('answer')
                else:
                    q_obj = math_question_map.get(question_id)
                    raw_answer = answer.get('answer')
                    is_correct = bool(q_obj and raw_answer is not None and check_written(raw_answer, q_obj.answer))
                    display_answer = raw_answer.replace('/', '-') if raw_answer else raw_answer

                if not q_obj:
                    continue

                if is_correct:
                    correct_counts[sec][mod] += 1

                questions[sec][mod].append({
                    'id': answer['questionID'],
                    'status': 'correct' if is_correct else 'incorrect',
                    'answer': display_answer,
                    'number': q_obj.number,
                    'time_spent': time_spent
                })
            except Exception:
                continue

    score = _score_from_counts(test_mode, correct_counts)

    testreview = TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False
    ).order_by('-created_at').first()

    english_total_correct = correct_counts['english']['m1'] + correct_counts['english']['m2']
    math_total_correct = correct_counts['math']['m1'] + correct_counts['math']['m2']

    english_total_time = time_spent_totals['english']['m1'] + time_spent_totals['english']['m2']
    math_total_time = time_spent_totals['math']['m1'] + time_spent_totals['math']['m2']

    total_correct = english_total_correct + math_total_correct

    stats = {
        'total': total_correct,
        'test': test_obj.name,
        'english_time': english_total_time,
        'math_time': math_total_time,
        'time_spent': english_total_time + math_total_time,
    }

    return {
        'is_complete': True,
        'status': status,
        'score': score,
        'stats': stats,
        'questions': questions,
        'testreview': testreview,
        'key': testreview.key if testreview else '',
        'test_mode': test_mode,
        'has_english': has_english,
        'has_math': has_math,
    }


def recalculate_practice_tests_progress(classroom, student):
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=student,
        role='student',
        status='approved'
    ).first()

    if not membership:
        return

    total_items = Test.objects.count()
    completed_items = TestReview.objects.filter(user=student).exclude(score__isnull=True).count()
    activity_count = TestModule.objects.filter(user=student).count()
    last_module = TestModule.objects.filter(user=student).order_by('-created_at').first()
    last_activity_at = last_module.created_at if last_module else None

    completion_percent = 0
    if total_items > 0:
        completion_percent = round((completed_items / total_items) * 100, 2)

    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='practice_tests',
        defaults={
            'completion_percent': completion_percent,
            'completed_items': completed_items,
            'total_items': total_items,
            'activity_count': activity_count,
            'last_activity_at': last_activity_at,
        }
    )

def recalculate_vocabulary_progress(classroom, student):
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=student,
        role='student',
        status='approved'
    ).first()

    if not membership:
        return

    total_items = VocabularyUnit.objects.count()

    # Временная логика: completed_items = 0, пока нет отдельной completion-модели
    completed_items = 0
    activity_count = 0
    last_activity_at = None

    completion_percent = 0
    if total_items > 0:
        completion_percent = round((completed_items / total_items) * 100, 2)

    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='vocabulary',
        defaults={
            'completion_percent': completion_percent,
            'completed_items': completed_items,
            'total_items': total_items,
            'activity_count': activity_count,
            'last_activity_at': last_activity_at,
        }
    )

def recalculate_admissions_progress(classroom, student):
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=student,
        role='student',
        status='approved'
    ).first()

    if not membership:
        return

    total_items = len(ADMISSIONS_SECTIONS) if 'ADMISSIONS_SECTIONS' in globals() else 0
    completed_items = 0
    activity_count = 0
    last_activity_at = None

    completion_percent = 0
    if total_items > 0:
        completion_percent = round((completed_items / total_items) * 100, 2)

    StudentProgress.objects.update_or_create(
        classroom=classroom,
        student=student,
        section='admissions',
        defaults={
            'completion_percent': completion_percent,
            'completed_items': completed_items,
            'total_items': total_items,
            'activity_count': activity_count,
            'last_activity_at': last_activity_at,
        }
    )

def recalculate_student_progress_for_classroom(classroom, student):
    recalculate_practice_tests_progress(classroom, student)
    recalculate_vocabulary_progress(classroom, student)
    recalculate_admissions_progress(classroom, student)

@login_required(login_url='/login/')
def classroom_progress_dashboard(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    student_memberships = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student',
        status='approved'
    ).select_related('user')

    should_refresh = request.GET.get('refresh') == '1'
    if should_refresh:
        for membership in student_memberships:
            recalculate_student_progress_for_classroom(classroom, membership.user)

    progress_records = StudentProgress.objects.filter(
        classroom=classroom
    ).select_related('student').order_by('student__username', 'section')

    grouped_progress = {}
    for record in progress_records:
        student_id = record.student.id
        if student_id not in grouped_progress:
            grouped_progress[student_id] = {
                'student': record.student,
                'practice_tests': None,
                'vocabulary': None,
                'admissions': None,
            }
        grouped_progress[student_id][record.section] = record

    return render(request, 'sat/classroom_progress_dashboard.html', {
        'classroom': classroom,
        'grouped_progress': grouped_progress.values(),
        'refreshed': should_refresh,
    })

@login_required(login_url='/login/')
def classroom_student_practice_progress(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    recalculate_student_progress_for_classroom(classroom, student)

    access_map = get_membership_section_access_map(membership)
    tests = _get_membership_allowed_tests(membership) if access_map.get('practice_tests') else []
    test_rows = _build_test_progress_rows(student, tests)
    practice_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='practice_tests'
    ).first()

    return render(request, 'sat/classroom_student_practice_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': access_map,
        'practice_progress': practice_progress,
        'test_rows': test_rows,
    })


@login_required(login_url='/login/')
def classroom_student_vocab_progress(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    recalculate_student_progress_for_classroom(classroom, student)

    vocab_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='vocabulary'
    ).first()
    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/classroom_student_vocab_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': get_membership_section_access_map(membership),
        'vocab_progress': vocab_progress,
        'units': units,
        'total_words': sum(unit.words.filter(is_active=True).count() for unit in units),
    })


@login_required(login_url='/login/')
def classroom_student_admission_progress(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    recalculate_student_progress_for_classroom(classroom, student)

    admission_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='admissions'
    ).first()

    return render(request, 'sat/classroom_student_admission_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': get_membership_section_access_map(membership),
        'admission_progress': admission_progress,
        'admission_sections': ADMISSIONS_SECTIONS,
    })


@login_required(login_url='/login/')
def classroom_student_review_results(request, classroom_id, student_id, test_name):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user
    test_obj = get_object_or_404(Test, name=test_name)

    result_context = _build_test_results_context_for_user(test_obj, student)
    if not result_context.get('is_complete'):
        return HttpResponse("Student has not finished all required modules for this test.")

    selected_review = result_context.get('testreview')

    context = {
        'user': request.user,
        'display_user': student,
        'classroom': classroom,
        'review_student': student,
        'is_teacher_review': True,
        'key': selected_review.key if selected_review else '',
        'selected_review_key': selected_review.key if selected_review else '',
        'selected_review': selected_review,
        'domains': selected_review.domains if selected_review else False,
    }
    context.update(result_context)

    return render(request, 'test/results.html', context)


@login_required(login_url='/login/')
def classroom_student_review_question(request, classroom_id, student_id, key, section, module, id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden("You can manage only your own classrooms.")

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user

    review = TestReview.objects.filter(key=key).select_related('user', 'test', 'makeup_test').first()
    if not review or review.user_id != student.id:
        return HttpResponse('This review is no longer available. A new retake may already be in progress.')

    if review.score is None:
        return HttpResponse('Review is unavailable because a retake is currently in progress.')

    module_obj = TestModule.objects.filter(
        test=review.test,
        user=review.user,
        section=section,
        module=module,
        attempt_id=review.attempt_id
    ).first()

    if not module_obj:
        return HttpResponse('Review for this section is unavailable because a retake is currently in progress.')

    prev, answer, new = module_obj.find_answer(question_id=id)
    prev = reverse('classroom_student_review_question', args=[classroom.id, student.id, key, section, module, prev]) if prev else ''
    new = reverse('classroom_student_review_question', args=[classroom.id, student.id, key, section, module, new]) if new else ''

    if section == 'english':
        question = English_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_eng.html', {
            'question': question,
            'answered': answer,
            'prev': prev,
            'next': new,
            'test': review.test,
            'is_teacher_review': True,
            'classroom': classroom,
            'review_student': student,
        })

    if section == 'math':
        question = Math_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_math.html', {
            'question': question,
            'answered': answer,
            'prev': prev,
            'next': new,
            'test': review.test,
            'is_teacher_review': True,
            'classroom': classroom,
            'review_student': student,
        })

    return HttpResponse('Invalid section')


def get_classroom_access_for_user(user, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if user.is_superuser:
        return classroom, 'admin', None

    if classroom.teacher_id == user.id:
        return classroom, 'teacher', None

    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=user,
        role='student',
        status='approved'
    ).first()

    if membership:
        return classroom, 'student', membership

    return classroom, None, None

@login_required(login_url='/login/')
def classroom_chat(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom chat."
        )

    messages_qs = ChatMessage.objects.filter(
        classroom=classroom,
        is_deleted=False
    ).select_related('sender').order_by('created_at')

    last_message = messages_qs.last()
    last_message_id = last_message.id if last_message else 0

    return render(request, 'sat/classroom_chat.html', {
        'classroom': classroom,
        'chat_messages': messages_qs,
        'role': role,
        'last_message_id': last_message_id,
    })

@login_required(login_url='/login/')
def send_classroom_message(request, classroom_id):
    if request.method != 'POST':
        return redirect('classroom_chat', classroom_id=classroom_id)

    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)
        return redirect_response

    if role is None:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Access denied.'}, status=403)
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom chat."
        )

    message_text = request.POST.get('message', '').strip()
    uploaded_file = request.FILES.get('file')

    if not message_text and not uploaded_file:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Message or file is required.'}, status=400)
        messages.error(request, "Message or file is required.")
        return redirect('classroom_chat', classroom_id=classroom.id)

    chat_message = ChatMessage.objects.create(
        classroom=classroom,
        sender=request.user,
        message=message_text if message_text else None,
        file=uploaded_file if uploaded_file else None,
        is_deleted=False,
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        full_name = chat_message.sender.get_full_name().strip()
        display_name = full_name if full_name else chat_message.sender.username

        initials = ""
        if chat_message.sender.first_name:
            initials += chat_message.sender.first_name[:1].upper()
        if chat_message.sender.last_name:
            initials += chat_message.sender.last_name[:1].upper()
        if not initials:
            initials = chat_message.sender.username[:1].upper()

        return JsonResponse({
            'ok': True,
            'message': {
                'id': chat_message.id,
                'author': display_name,
                'initials': initials,
                'is_mine': True,
                'created_at': chat_message.created_at.strftime('%Y-%m-%d %H:%M'),
                'text': chat_message.message or '',
                'file_url': chat_message.file.url if chat_message.file else '',
                'file_name': chat_message.file.name.split('/')[-1] if chat_message.file else '',
                'delete_message_url': f'/sat/classroom/{classroom.id}/chat/message/{chat_message.id}/delete/',
                'delete_file_url': f'/sat/classroom/{classroom.id}/chat/message/{chat_message.id}/delete-file/' if chat_message.file else '',
                'role': role,
            }
        })

    return redirect('classroom_chat', classroom_id=classroom.id)

@login_required(login_url='/login/')
def delete_classroom_message(request, classroom_id, message_id):
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'POST method required.'}, status=405)
        messages.error(request, "Deleting chat messages requires POST.")
        return redirect('classroom_chat', classroom_id=classroom_id)

    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)
        return redirect_response

    if role not in ['teacher', 'admin']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Only teacher can delete messages.'}, status=403)
        return HttpResponseForbidden("Only teacher can delete messages.")

    chat_message = get_object_or_404(
        ChatMessage,
        id=message_id,
        classroom=classroom
    )

    if chat_message.file:
        chat_message.file.delete(save=False)

    chat_message.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'message_id': message_id,
            'action': 'delete_message',
        })

    messages.success(request, "Chat message deleted.")
    return redirect('classroom_chat', classroom_id=classroom.id)

@login_required(login_url='/login/')
def delete_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can delete only your own classrooms.")

    if request.method != 'POST':
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    classroom_name = classroom.name
    classroom.delete()

    messages.success(request, f'Classroom "{classroom_name}" was deleted.')
    return redirect('teacher_classroom_list')

@login_required(login_url='/login/')
def delete_classroom_message_file(request, classroom_id, message_id):
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'POST method required.'}, status=405)
        messages.error(request, "Deleting chat files requires POST.")
        return redirect('classroom_chat', classroom_id=classroom_id)

    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)
        return redirect_response

    if role not in ['teacher', 'admin']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Only teacher can delete files.'}, status=403)
        return HttpResponseForbidden("Only teacher can delete files.")

    chat_message = get_object_or_404(
        ChatMessage,
        id=message_id,
        classroom=classroom
    )

    if chat_message.file:
        chat_message.file.delete(save=False)
        chat_message.file = None
        chat_message.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'message_id': message_id,
            'action': 'delete_file',
        })

    messages.success(request, "File deleted from message.")
    return redirect('classroom_chat', classroom_id=classroom.id)

@login_required(login_url='/login/')
def edit_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can edit only your own classrooms.")

    if request.method != 'POST':
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        messages.error(request, "Classroom name is required.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    classroom.name = name
    classroom.description = description
    classroom.save()

    messages.success(request, "Classroom updated successfully.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def resolve_classroom_and_role(request, classroom_id):
    classroom = Classroom.objects.filter(id=classroom_id).first()

    if not classroom:
        messages.error(request, "This classroom does not exist anymore.")
        return None, None, None, redirect('sat_menu')

    if request.user.is_superuser:
        return classroom, 'admin', None, None

    if classroom.teacher_id == request.user.id:
        return classroom, 'teacher', None, None

    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=request.user,
        role='student',
        status='approved'
    ).prefetch_related('section_access').first()

    if membership:
        return classroom, 'student', membership, None

    return classroom, None, None, None

@login_required(login_url='/login/')
def fetch_classroom_messages(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return JsonResponse({'ok': False, 'error': 'Classroom not found.'}, status=404)

    if role is None:
        return JsonResponse({'ok': False, 'error': 'Access denied.'}, status=403)

    last_id = request.GET.get('last_id')
    try:
        last_id = int(last_id) if last_id else 0
    except ValueError:
        last_id = 0

    messages_qs = ChatMessage.objects.filter(
        classroom=classroom,
        is_deleted=False,
        id__gt=last_id
    ).select_related('sender').order_by('id')

    result = []

    for item in messages_qs:
        full_name = item.sender.get_full_name().strip()
        display_name = full_name if full_name else item.sender.username

        initials = ""
        if item.sender.first_name:
            initials += item.sender.first_name[:1].upper()
        if item.sender.last_name:
            initials += item.sender.last_name[:1].upper()
        if not initials:
            initials = item.sender.username[:1].upper()

        result.append({
            'id': item.id,
            'author': display_name,
            'initials': initials,
            'is_mine': item.sender_id == request.user.id,
            'created_at': item.created_at.strftime('%Y-%m-%d %H:%M'),
            'text': item.message or '',
            'file_url': item.file.url if item.file else '',
            'file_name': item.file.name.split('/')[-1] if item.file else '',
            'delete_message_url': f'/sat/classroom/{classroom.id}/chat/message/{item.id}/delete/',
            'delete_file_url': f'/sat/classroom/{classroom.id}/chat/message/{item.id}/delete-file/' if item.file else '',
        })

    return JsonResponse({
        'ok': True,
        'messages': result,
    })

@login_required(login_url='/login/')
def teacher_vocabulary_units(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can manage vocabulary.")

    units = VocabularyUnit.objects.all().order_by('order', 'title')

    return render(request, 'sat/teacher_vocabulary_units.html', {
        'units': units,
    })


@login_required(login_url='/login/')
def create_vocabulary_unit(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can create vocabulary units.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        order_raw = request.POST.get('order', '').strip()
        description = request.POST.get('description', '').strip()

        if not title:
            messages.error(request, "Unit title is required.")
            return redirect('create_vocabulary_unit')

        try:
            order = int(order_raw)
        except (TypeError, ValueError):
            messages.error(request, "Unit order must be a valid integer.")
            return redirect('create_vocabulary_unit')

        if VocabularyUnit.objects.filter(order=order).exists():
            messages.error(request, "A vocabulary unit with this order already exists.")
            return redirect('create_vocabulary_unit')

        unit = VocabularyUnit.objects.create(
            title=title,
            order=order,
            description=description,
        )

        messages.success(request, "Vocabulary unit created successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_unit.html')


@login_required(login_url='/login/')
def teacher_vocabulary_unit_detail(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can manage vocabulary.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)
    words = VocabularyWord.objects.filter(unit=unit).order_by('word')
    questions = VocabularyQuestion.objects.filter(unit=unit).order_by('id')

    return render(request, 'sat/teacher_vocabulary_unit_detail.html', {
        'unit': unit,
        'words': words,
        'questions': questions,
    })


@login_required(login_url='/login/')
def create_vocabulary_word(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can add vocabulary words.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)

    if request.method == 'POST':
        word = request.POST.get('word', '').strip()
        meaning = request.POST.get('meaning', '').strip()
        example = request.POST.get('example', '').strip()

        if not word:
            messages.error(request, "Word is required.")
            return redirect('create_vocabulary_word', unit_id=unit.id)

        if not meaning:
            messages.error(request, "Meaning is required.")
            return redirect('create_vocabulary_word', unit_id=unit.id)

        VocabularyWord.objects.create(
            unit=unit,
            word=word,
            meaning=meaning,
            example=example,
        )

        messages.success(request, "Vocabulary word added successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_word.html', {
        'unit': unit,
    })

def parse_bulk_vocabulary_text(raw_text):
    parsed = []
    bad_lines = []

    text = raw_text.replace('\r\n', '\n').replace('\r', '\n')

    # Склеиваем переносы из PDF: новая запись начинается только с "123. ..."
    merged_lines = []
    current = ""

    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r'^\d+\.\s+', line):
            if current:
                merged_lines.append(current.strip())
            current = line
        else:
            current += " " + line

    if current:
        merged_lines.append(current.strip())

    for original in merged_lines:
        line = re.sub(r'^\d+\.\s*', '', original).strip()

        parts = re.split(r'\s+[—–-]\s+', line, maxsplit=1)

        if len(parts) != 2:
            bad_lines.append(original)
            continue

        word = parts[0].strip()
        meaning = parts[1].strip()

        if not word or not meaning:
            bad_lines.append(original)
            continue

        parsed.append({
            'word': word,
            'meaning': meaning,
            'example': '',
        })

    return parsed, bad_lines


@login_required(login_url='/login/')
def bulk_import_vocabulary_words(request):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can import vocabulary words.")

    if request.method == 'POST':
        raw_text = request.POST.get('raw_text', '').strip()

        if not raw_text:
            messages.error(request, "Paste the vocabulary text first.")
            return redirect('bulk_import_vocabulary_words')

        parsed_items, bad_lines = parse_bulk_vocabulary_text(raw_text)

        if not parsed_items:
            messages.error(request, "Nothing valid was parsed. Check the text format.")
            return redirect('bulk_import_vocabulary_words')

        # Убираем дубли:
        # 1) уже существующие в базе
        # 2) повторы внутри самого вставленного текста
        existing_words = {
            w.strip().lower()
            for w in VocabularyWord.objects.values_list('word', flat=True)
        }

        cleaned_items = []
        seen_in_import = set()
        skipped_duplicates = 0

        for item in parsed_items:
            key = item['word'].strip().lower()

            if key in existing_words or key in seen_in_import:
                skipped_duplicates += 1
                continue

            cleaned_items.append(item)
            seen_in_import.add(key)

        if not cleaned_items:
            messages.warning(
                request,
                f"All parsed words were duplicates. Bad lines: {len(bad_lines)}."
            )
            request.session['bulk_vocab_bad_lines'] = bad_lines[:100]
            return redirect('bulk_import_vocabulary_words')

        with transaction.atomic():
            # Гарантируем наличие Unit 1..50
            units_by_order = {u.order: u for u in VocabularyUnit.objects.all()}

            for i in range(1, 51):
                if i not in units_by_order:
                    units_by_order[i] = VocabularyUnit.objects.create(
                        order=i,
                        title=f"Unit {i}",
                        description=f"Vocabulary Unit {i}",
                        is_active=True,
                    )

            units = [units_by_order[i] for i in range(1, 51)]

            # Сколько слов уже в каждом юните
            unit_counts = {
                row['unit']: row['count']
                for row in VocabularyWord.objects.values('unit').annotate(count=Count('id'))
            }

            to_create = []
            item_index = 0

            for unit in units:
                current_count = unit_counts.get(unit.id, 0)
                free_slots = max(0, 25 - current_count)

                while free_slots > 0 and item_index < len(cleaned_items):
                    item = cleaned_items[item_index]

                    to_create.append(
                        VocabularyWord(
                            unit=unit,
                            word=item['word'],
                            meaning=item['meaning'],
                            example=item['example'],
                            is_active=True,
                        )
                    )

                    item_index += 1
                    free_slots -= 1

                if item_index >= len(cleaned_items):
                    break

            if to_create:
                VocabularyWord.objects.bulk_create(to_create, batch_size=500)

        imported_count = len(to_create)
        not_imported_count = len(cleaned_items) - imported_count

        if bad_lines:
            request.session['bulk_vocab_bad_lines'] = bad_lines[:100]
        else:
            request.session.pop('bulk_vocab_bad_lines', None)

        if not_imported_count > 0:
            messages.warning(
                request,
                f"Imported {imported_count} words. "
                f"Skipped duplicates: {skipped_duplicates}. "
                f"Unparsed lines: {len(bad_lines)}. "
                f"{not_imported_count} words were not imported because all 50 units are full."
            )
        else:
            messages.success(
                request,
                f"Imported {imported_count} words. "
                f"Skipped duplicates: {skipped_duplicates}. "
                f"Unparsed lines: {len(bad_lines)}."
            )

        return redirect('teacher_vocabulary_units')

    bad_lines = request.session.pop('bulk_vocab_bad_lines', [])
    return render(request, 'sat/bulk_import_vocabulary_words.html', {
        'bad_lines': bad_lines,
    })

@login_required(login_url='/login/')
def create_vocabulary_question(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can add vocabulary questions.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)

    if request.method == 'POST':
        # Determine which content to use based on the mode
        question_rich = request.POST.get('question_rich', '').strip()
        question_latex = request.POST.get('question_latex', '').strip()

        option_a_rich = request.POST.get('option_a_rich', '').strip()
        option_a_latex = request.POST.get('option_a_latex', '').strip()

        option_b_rich = request.POST.get('option_b_rich', '').strip()
        option_b_latex = request.POST.get('option_b_latex', '').strip()

        option_c_rich = request.POST.get('option_c_rich', '').strip()
        option_c_latex = request.POST.get('option_c_latex', '').strip()

        option_d_rich = request.POST.get('option_d_rich', '').strip()
        option_d_latex = request.POST.get('option_d_latex', '').strip()

        correct_answer = request.POST.get('correct_answer', '').strip().upper()

        # Use rich text if available, otherwise use LaTeX
        question_text = question_rich or question_latex
        option_a = option_a_rich or option_a_latex
        option_b = option_b_rich or option_b_latex
        option_c = option_c_rich or option_c_latex
        option_d = option_d_rich or option_d_latex

        if not all([question_text, option_a, option_b, option_c, option_d, correct_answer]):
            messages.error(request, "All fields are required.")
            return redirect('create_vocabulary_question', unit_id=unit.id)

        if correct_answer not in ['A', 'B', 'C', 'D']:
            messages.error(request, "Correct answer must be A, B, C, or D.")
            return redirect('create_vocabulary_question', unit_id=unit.id)

        VocabularyQuestion.objects.create(
            unit=unit,
            question=question_text,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_answer=correct_answer,
        )

        messages.success(request, "Vocabulary question added successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_question.html', {
        'unit': unit,
    })

def get_student_allowed_practice_tests_queryset(membership):
    custom_access_items = StudentPracticeTestAccess.objects.filter(
        membership=membership,
        has_access=True
    )

    allowed_test_ids = custom_access_items.values_list('test_id', flat=True)
    return Test.objects.filter(pk__in=allowed_test_ids).distinct().order_by('name')

def get_test_mode(test):
    has_english = English_Question.objects.filter(test=test).exists()
    has_math = Math_Question.objects.filter(test=test).exists()

    if has_english and has_math:
        return 'full'
    if has_english:
        return 'ebrw_only'
    if has_math:
        return 'math_only'
    return 'empty'


def get_test_sequence(test):
    def normalize_module(module):
        if module == 'module_1':
            return 'm1'
        if module == 'module_2':
            return 'm2'
        return module

    english_modules = sorted(
        set(English_Question.objects.filter(test=test).values_list('module', flat=True)),
        key=lambda m: ['module_1', 'module_2'].index(m) if m in ['module_1', 'module_2'] else 99
    )
    math_modules = sorted(
        set(Math_Question.objects.filter(test=test).values_list('module', flat=True)),
        key=lambda m: ['module_1', 'module_2'].index(m) if m in ['module_1', 'module_2'] else 99
    )

    sequence = []
    for module in english_modules:
        sequence.append(('english', normalize_module(module)))
    for module in math_modules:
        sequence.append(('math', normalize_module(module)))
    return sequence


def get_makeup_test_sequence(makeup_test):
    def normalize_module(module):
        if module == 'module_1':
            return 'm1'
        if module == 'module_2':
            return 'm2'
        return module

    def module_sort_key(module):
        return ['module_1', 'module_2'].index(module) if module in ['module_1', 'module_2'] else 99

    english_modules = sorted(
        set(makeup_test.english_questions.values_list('module', flat=True)),
        key=module_sort_key
    )
    math_modules = sorted(
        set(makeup_test.math_questions.values_list('module', flat=True)),
        key=module_sort_key
    )

    sequence = []
    for module in english_modules:
        sequence.append(('english', normalize_module(module)))
    for module in math_modules:
        sequence.append(('math', normalize_module(module)))
    return sequence

def get_current_test_step(test_stage):
    sequence = get_test_sequence(test_stage.test)

    if not sequence:
        return None

    if test_stage.stage < 1 or test_stage.stage > len(sequence):
        return None

    return sequence[test_stage.stage - 1]


def advance_test_stage(test_stage):
    sequence = get_test_sequence(test_stage.test)

    if not sequence:
        return True

    if test_stage.stage >= len(sequence):
        return True

    test_stage.stage += 1
    test_stage.save()
    return False


def get_section_start_stage(test, section):
    sequence = get_test_sequence(test)

    for index, (seq_section, seq_module) in enumerate(sequence, start=1):
        if seq_section == section:
            return index

    return None

@login_required(login_url='/login/')
def classroom_start_practise(request, classroom_id, pk):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role in ['teacher', 'admin']:
        test = get_object_or_404(Test, name=pk)
    elif role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Practice Tests."
            )

        allowed_tests = get_student_allowed_practice_tests_queryset(membership)
        test = get_object_or_404(allowed_tests, name=pk)
    else:
        return HttpResponseForbidden("Access denied.")

    # Check if test is already completed
    completed_review = TestReview.objects.filter(
        user=request.user,
        test=test,
        score__isnull=False
    ).order_by('-created_at').first()
    
    if completed_review:
        return redirect('results', test=test.name)

    # Check if there's an in-progress attempt
    has_active_attempt = TestModule.objects.filter(
        user=request.user,
        test=test
    ).exists()

    return render(request, 'test/test_modules.html', {
        'test': test,
        'classroom': classroom,
        'role': role,
        'has_active_attempt': has_active_attempt,
        'start_url': reverse('classroom_test', kwargs={
            'classroom_id': classroom.id,
            'pk': test.name
        })
    })

@login_required(login_url='/login/')
def classroom_module_test(request, classroom_id, pk):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if role in ['teacher', 'admin']:
        test = get_object_or_404(Test, name=pk)
    elif role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Practice Tests."
            )

        allowed_tests = get_student_allowed_practice_tests_queryset(membership)
        test = get_object_or_404(allowed_tests, name=pk)
    else:
        return HttpResponseForbidden("Access denied.")

    user = request.user
    sequence = get_test_sequence(test)
    if not sequence:
        return HttpResponse('Questions are not found')

    test_stage, created = TestStage.objects.get_or_create(
        user=user,
        test=test,
        defaults={'stage': 1}
    )

    current_step = get_current_test_step(test_stage)
    if current_step is None:
        return redirect('results', test=test.name)

    section, module = current_step

    existing_module = TestModule.objects.filter(
        test=test,
        section=section,
        module=module,
        user=user,
        attempt_id=test_stage.attempt_id
    )

    if existing_module.exists():
        finished = advance_test_stage(test_stage)
        if finished:
            return redirect('results', test=test.name)
        return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)

    custom_time_seconds = None
    if user.groups.filter(name='OFFLINE').exists():
        profile, created = UserProfile.objects.get_or_create(user=user)
        if section == 'english':
            custom_time_seconds = profile.get_english_time_seconds()
        elif section == 'math':
            custom_time_seconds = profile.get_math_time_seconds()

    if section == 'english':
        questions = English_Question.objects.filter(
            test=test,
            module=f'module_{module[1]}'
        ).order_by('number')

        if not questions.exists():
            finished = advance_test_stage(test_stage)
            if finished:
                return redirect('results', test=test.name)
            return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)

        return render(request, 'test/test_eng.html', {
            'questions': questions,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds,
            'classroom': classroom,
        })

    if section == 'math':
        questions = Math_Question.objects.filter(
            test=test,
            module=f'module_{module[1]}'
        ).order_by('number')

        if not questions.exists():
            finished = advance_test_stage(test_stage)
            if finished:
                return redirect('results', test=test.name)
            return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)

        questions_data = []
        for q in questions:
            questions_data.append({
                "id": q.id,
                "passage": q.passage or "",
                "number": q.number,
                "question": q.question or "",
                "a": q.get_a() if hasattr(q, "get_a") else "",
                "b": q.get_b() if hasattr(q, "get_b") else "",
                "c": q.get_c() if hasattr(q, "get_c") else "",
                "d": q.get_d() if hasattr(q, "get_d") else "",
                "type": str(q.written),
                "graph": q.get_graph() if hasattr(q, "get_graph") else "",
            })
        return render(request, 'test/test_math.html', {
            'questions': questions,
            'questions_data': questions_data,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds,
            'classroom': classroom,
        })

    return HttpResponse("You dont have permission")


@login_required(login_url='/login/')
def lesson_detail(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('package', 'question_type'), id=lesson_id)

    has_purchase = PurchasedLessonPackage.objects.filter(
        user=request.user,
        package=lesson.package
    ).exists()

    if not has_purchase and not request.user.is_staff and not request.user.is_superuser and not is_teacher(request.user):
        return HttpResponseForbidden("This lesson is not assigned to your account.")

    progress, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
    questions = lesson.get_random_questions()

    return render(request, 'sat/lesson_detail.html', {
        'lesson': lesson,
        'progress': progress,
        'questions': questions,
    })

@login_required(login_url='/login/')
def update_classroom_practice_test_access(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    memberships = list(
        ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student',
            status='approved'
        ).select_related('user').prefetch_related('section_access')
    )

    eligible_memberships = [
        membership
        for membership in memberships
        if get_membership_section_access_map(membership).get('practice_tests')
    ]

    tests = list(Test.objects.all().distinct())

    def get_day_number(test):
        try:
            name = str(test.name).strip().lower()
            if name.startswith('day'):
                digits = ''.join(ch for ch in name if ch.isdigit())
                if digits:
                    return int(digits)
            return 999999
        except Exception:
            return 999999

    tests = sorted(tests, key=lambda t: (get_day_number(t), str(t.name)))
    all_test_ids = {str(test.pk) for test in tests}

    selected_test_ids = set()
    access_mode = 'selected'

    if eligible_memberships:
        first_membership = eligible_memberships[0]
        selected_test_ids = set(
            str(pk) for pk in StudentPracticeTestAccess.objects.filter(
                membership=first_membership,
                has_access=True
            ).values_list('test__pk', flat=True)
        )

        if selected_test_ids == all_test_ids and all_test_ids:
            access_mode = 'all'
        else:
            access_mode = 'selected'

    if request.method == 'POST':
        access_mode = request.POST.get('access_mode', 'selected')
        selected_test_ids = set(request.POST.getlist('tests'))

        if not eligible_memberships:
            messages.error(
                request,
                "There are no approved students with Practice Tests section enabled."
            )
            return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

        if access_mode == 'selected' and not selected_test_ids:
            messages.error(request, "Select at least one practice test.")
            return render(request, 'sat/update_classroom_practice_test_access.html', {
                'classroom': classroom,
                'tests': tests,
                'eligible_count': len(eligible_memberships),
                'total_students_count': len(memberships),
                'selected_test_ids': selected_test_ids,
                'access_mode': 'selected',
            })

        membership_ids = [membership.id for membership in eligible_memberships]

        StudentPracticeTestAccess.objects.filter(
            membership_id__in=membership_ids
        ).delete()

        if access_mode == 'all':
            selected_tests = tests
            selected_test_ids = {str(test.pk) for test in tests}
        else:
            selected_tests = [test for test in tests if str(test.pk) in selected_test_ids]

        bulk_items = []
        for membership in eligible_memberships:
            for test in selected_tests:
                bulk_items.append(
                    StudentPracticeTestAccess(
                        membership=membership,
                        test=test,
                        has_access=True
                    )
                )

        if bulk_items:
            StudentPracticeTestAccess.objects.bulk_create(bulk_items)

        if access_mode == 'all':
            messages.success(
                request,
                f'All practice tests were granted for {len(eligible_memberships)} students.'
            )
        else:
            messages.success(
                request,
                f'Selected practice tests were granted for {len(eligible_memberships)} students.'
            )

        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    return render(request, 'sat/update_classroom_practice_test_access.html', {
        'classroom': classroom,
        'tests': tests,
        'eligible_count': len(eligible_memberships),
        'total_students_count': len(memberships),
        'selected_test_ids': selected_test_ids,
        'access_mode': access_mode,
    })