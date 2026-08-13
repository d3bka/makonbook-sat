from multiprocessing import context
from urllib import request

from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, HttpResponseRedirect, Http404, JsonResponse
from apps.base.decorators import allowed_users
from django.contrib.auth.models import Group, User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.conf import settings
from satmakon.settings import BASE_DIR
from .libs import calculator
from .answer_matching import check_english_answer, reference_answer
from .vocabulary_progress import (
    build_unit_progress_rows,
    get_vocabulary_summary,
    get_weak_words,
    record_word_review,
    sync_vocabulary_review_progress,
    sync_vocabulary_student_progress,
)
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta, datetime
from .libs.certificate.certificate import create_certificate
from math import floor, ceil
from django.contrib import messages  # Added for user feedback
from apps.base.models import UserProfile
from django.core.cache import cache
from django.db.models import Q, Avg, Prefetch, Max
import json
import logging
import random
import re
import uuid
from django.db.models import Count
from django.db import transaction, IntegrityError
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from collections import defaultdict
from django.urls import reverse
from django.templatetags.static import static as static_url
from django.db import close_old_connections
from django.contrib.auth import authenticate, login, logout
from urllib.parse import urlparse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import ValidationError
from .support_forms import SupportTeacherSelfAvailabilityForm, SupportTeacherSelfProfileForm
from .student_goal_forms import StudentGoalProfileForm

logger = logging.getLogger(__name__)


try:
    from apps.apclasses.models import APExamEvent
except Exception:  # keeps SAT views import-safe if AP app is unavailable
    APExamEvent = None


def home(request):

    if request.user.is_authenticated:
        return redirect('sat_menu')

    return render(request, "landing/home.html")



def loginPage(request):

    if request.user.is_authenticated:
        return redirect('sat_menu')

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:

            login(request, user)

            return redirect("sat_menu")

    return render(request, "login.html")





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

    classroom = _get_classroom_context_from_id(user, request.POST.get('classroom_id'), test_obj=test)

    if classroom is None and not user_has_test_access(user, test):
        return HttpResponse(
            f"Test '{pk}' is not assigned to your account.",
            status=403
        )

    stage, _ = _get_or_create_regular_test_stage(user, test, stage=1, classroom=classroom)

    # Try to restart the full test
    response = stage.resolve()

    if response:
        if classroom:
            return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)
        return redirect('test', pk=test.name)
    else:
        # Retake limit exceeded
        user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'
        
        return render(request, 'sat/retake_limit_exceeded.html', {
            'test_name': pk,
            'section': None,
            'retakes_used': stage.retake_count,
            'max_retakes': stage.get_max_retakes(),
            'user_group': user_group,
            'classroom': classroom,
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


def _normalize_live_test_answer(question, section, value):
    """Bound and normalize live answers before they are persisted.

    Multiple-choice questions accept only A-D (or blank). Open responses keep the
    student's text, but cap it so a forged request cannot store unbounded payloads.
    """
    if value is None:
        return None

    section = _normalize_test_section(section)
    if section == 'english' and getattr(question, 'is_open_text', False):
        text = str(value).replace('\x00', '').strip()
        return text[:4000] or None
    if section == 'math' and bool(getattr(question, 'written', False)):
        text = str(value).replace('\x00', '').strip()
        return text[:120] or None

    choice = str(value).strip().upper()
    return choice if choice in {'A', 'B', 'C', 'D'} else None


def _validate_regular_module_answers(test_obj, section, module, answers):
    section = _normalize_test_section(section)
    module = _normalize_test_module(module)
    module_db = _module_db_name(module)

    if section not in ['english', 'math'] or module not in ['m1', 'm2']:
        return False, 'Invalid section/module.', []

    question_model = English_Question if section == 'english' else Math_Question
    question_map = question_model.objects.filter(
        test=test_obj,
        module=module_db,
    ).in_bulk()
    expected_ids = set(question_map)

    if not expected_ids:
        return False, 'No questions exist for this test module.', []

    if not isinstance(answers, list):
        return False, 'answers must be a list.', []

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

        question = question_map.get(question_id)
        if question is None:
            return False, 'One or more answers do not belong to this test module.', []

        try:
            time_spent = max(int(item.get('time_spent', 0) or 0), 0)
        except (TypeError, ValueError):
            time_spent = 0

        submitted_ids.append(question_id)
        canonical_answers.append({
            'questionID': question_id,
            'answer': _normalize_live_test_answer(question, section, item.get('answer')),
            'time_spent': min(time_spent, 24 * 60 * 60),
        })

    if len(submitted_ids) != len(set(submitted_ids)):
        return False, 'Duplicate question IDs are not allowed.', []

    submitted_id_set = set(submitted_ids)
    missing_ids = expected_ids - submitted_id_set
    if missing_ids:
        return False, 'Submitted answers do not cover every question in this test module.', []

    return True, '', canonical_answers


def _validate_makeup_module_answers(makeup_test, section, module, answers):
    """Validate a Makeup module against its explicit question membership."""
    section = _normalize_test_section(section)
    module = _normalize_test_module(module)
    if section not in {'english', 'math'} or module not in {'m1', 'm2'}:
        return False, 'Invalid section/module.', []
    questions = makeup_test.get_module_questions(section, _module_db_name(module))
    question_map = {question.id: question for question in (questions or [])}
    if not question_map:
        return False, 'No questions exist for this makeup module.', []
    if not isinstance(answers, list):
        return False, 'answers must be a list.', []
    seen, canonical = set(), []
    for item in answers:
        if not isinstance(item, dict):
            return False, 'Every answer must be an object.', []
        raw_id = item.get('questionID') or item.get('question_id') or item.get('id')
        try:
            question_id = int(raw_id)
        except (TypeError, ValueError):
            return False, 'Invalid question ID.', []
        question = question_map.get(question_id)
        if question is None:
            return False, 'One or more answers do not belong to this makeup module.', []
        if question_id in seen:
            return False, 'Duplicate question IDs are not allowed.', []
        seen.add(question_id)
        try:
            time_spent = max(int(item.get('time_spent', 0) or 0), 0)
        except (TypeError, ValueError):
            time_spent = 0
        canonical.append({
            'questionID': question_id,
            'answer': _normalize_live_test_answer(question, section, item.get('answer')),
            'time_spent': min(time_spent, 24 * 60 * 60),
        })
    if set(seen) != set(question_map):
        return False, 'Submitted answers do not cover every question in this makeup module.', []
    return True, '', canonical


def _question_model_for_section(section):
    section = _normalize_test_section(section)
    if section == 'english':
        return English_Question
    if section == 'math':
        return Math_Question
    return None


def _module_questions_queryset(test_obj, section, module):
    question_model = _question_model_for_section(section)
    if question_model is None:
        return None
    return question_model.objects.filter(
        test=test_obj,
        module=_module_db_name(module),
    ).order_by('number', 'id')


def _module_duration_seconds(user, section):
    section = _normalize_test_section(section)
    default_seconds = 1920 if section == 'english' else 2100
    if user.is_authenticated and user.groups.filter(name='OFFLINE').exists():
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if section == 'english':
            return max(int(profile.get_english_time_seconds() or default_seconds), 1)
        if section == 'math':
            return max(int(profile.get_math_time_seconds() or default_seconds), 1)
    return default_seconds


def _safe_json_list(value, expected_length=None, default_factory=list):
    if not isinstance(value, list):
        value = default_factory()
    if expected_length is not None:
        value = list(value[:expected_length])
        while len(value) < expected_length:
            fallback = default_factory()
            value.append(fallback[len(value)] if len(fallback) > len(value) else None)
    return value


def _canonical_partial_module_answers(test_obj, section, module, answers):
    """Validate an autosave payload without requiring every question.

    Final submission still uses ``_validate_regular_module_answers`` and requires
    all question IDs. Drafts may be partial, but may never reference another test
    or module.
    """
    section = _normalize_test_section(section)
    module = _normalize_test_module(module)
    question_model = _question_model_for_section(section)
    if question_model is None or module not in {'m1', 'm2'}:
        return False, 'Invalid section/module.', []

    question_map = question_model.objects.filter(
        test=test_obj,
        module=_module_db_name(module),
    ).in_bulk()
    expected_ids = set(question_map)
    if not expected_ids:
        return False, 'No questions exist for this test module.', []

    if not isinstance(answers, list):
        return False, 'answers must be a list.', []

    seen = set()
    canonical = []
    for item in answers:
        if not isinstance(item, dict):
            return False, 'Every answer must be an object.', []
        question_id = item.get('questionID') or item.get('question_id') or item.get('id')
        if question_id in [None, '']:
            continue
        try:
            question_id = int(question_id)
        except (TypeError, ValueError):
            return False, 'Invalid question ID.', []
        if question_id not in expected_ids:
            return False, 'One or more answers do not belong to this test module.', []
        if question_id in seen:
            return False, 'Duplicate question IDs are not allowed.', []
        seen.add(question_id)
        try:
            time_spent = max(int(item.get('time_spent', 0) or 0), 0)
        except (TypeError, ValueError):
            time_spent = 0
        canonical.append({
            'questionID': question_id,
            'answer': _normalize_live_test_answer(question_map[question_id], section, item.get('answer')),
            'time_spent': min(time_spent, 24 * 60 * 60),
        })
    return True, '', canonical


def _canonical_partial_makeup_answers(makeup_test, section, module, answers):
    section = _normalize_test_section(section)
    module = _normalize_test_module(module)
    if section not in {'english', 'math'} or module not in {'m1', 'm2'}:
        return False, 'Invalid section/module.', []
    questions = makeup_test.get_module_questions(section, _module_db_name(module))
    question_map = {question.id: question for question in (questions or [])}
    if not question_map:
        return False, 'No questions exist for this makeup module.', []
    if not isinstance(answers, list):
        return False, 'answers must be a list.', []
    seen, canonical = set(), []
    for item in answers:
        if not isinstance(item, dict):
            return False, 'Every answer must be an object.', []
        raw_id = item.get('questionID') or item.get('question_id') or item.get('id')
        if raw_id in [None, '']:
            continue
        try:
            question_id = int(raw_id)
        except (TypeError, ValueError):
            return False, 'Invalid question ID.', []
        question = question_map.get(question_id)
        if question is None:
            return False, 'One or more answers do not belong to this makeup module.', []
        if question_id in seen:
            return False, 'Duplicate question IDs are not allowed.', []
        seen.add(question_id)
        try:
            time_spent = max(int(item.get('time_spent', 0) or 0), 0)
        except (TypeError, ValueError):
            time_spent = 0
        canonical.append({
            'questionID': question_id,
            'answer': _normalize_live_test_answer(question, section, item.get('answer')),
            'time_spent': min(time_spent, 24 * 60 * 60),
        })
    return True, '', canonical


def _ensure_makeup_module_draft(stage, section, module):
    duration_seconds = _module_duration_seconds(stage.user, section)
    draft, _ = MakeupTestModuleDraft.objects.get_or_create(
        user=stage.user,
        makeup_test=stage.makeup_test,
        attempt_id=stage.attempt_id,
        section=_normalize_test_section(section),
        module=_normalize_test_module(module),
        defaults={'deadline_at': timezone.now() + timedelta(seconds=duration_seconds)},
    )
    if not draft.deadline_at:
        draft.deadline_at = timezone.now() + timedelta(seconds=duration_seconds)
        draft.save(update_fields=['deadline_at', 'updated_at'])
    return draft


def _complete_makeup_answers_from_draft(makeup_test, section, module, draft):
    questions = list(makeup_test.get_module_questions(section, _module_db_name(module)) or [])
    lookup = {
        int(item.get('questionID')): item
        for item in (draft.answers or [])
        if isinstance(item, dict) and str(item.get('questionID', '')).isdigit()
    }
    return [
        {
            'questionID': question.id,
            'answer': lookup.get(question.id, {}).get('answer'),
            'time_spent': max(int(lookup.get(question.id, {}).get('time_spent', 0) or 0), 0),
        }
        for question in questions
    ]


def _makeup_redirect_url(makeup_test, stage):
    sequence = get_makeup_test_sequence(makeup_test)
    if 1 <= stage.stage <= len(sequence):
        return reverse('makeup_test_module', kwargs={'pk': makeup_test.name})
    return reverse('sat_menu')


def _submit_makeup_module_locked(stage, section, module, canonical_answers):
    existing = TestModule.objects.filter(
        user=stage.user,
        makeup_test=stage.makeup_test,
        test_type='makeup',
        section=section,
        module=module,
        attempt_id=stage.attempt_id,
    ).first()
    if existing:
        return existing, False
    module_obj = TestModule.objects.create(
        user=stage.user,
        makeup_test=stage.makeup_test,
        test_type='makeup',
        section=section,
        module=module,
        attempt_id=stage.attempt_id,
        answers=json.dumps({'answers': canonical_answers}),
    )
    MakeupTestModuleDraft.objects.filter(
        user=stage.user,
        makeup_test=stage.makeup_test,
        attempt_id=stage.attempt_id,
        section=section,
        module=module,
    ).delete()
    stage.stage += 1
    stage.save(update_fields=['stage', 'updated_at'])
    return module_obj, True


def _makeup_module_runtime(stage, section, module, questions):
    draft = _ensure_makeup_module_draft(stage, section, module)
    if _draft_remaining_seconds(draft) > 0:
        return {
            'redirect_url': None,
            'context': {
                'attempt_id': stage.attempt_id,
                'time_remaining_seconds': _draft_remaining_seconds(draft),
                'test_session_state': _draft_state_payload(draft, list(questions)),
                'draft_save_url': reverse('save_test_module_draft'),
            },
        }
    with transaction.atomic():
        locked = TestStage.objects.select_for_update().select_related('makeup_test').get(pk=stage.pk)
        sequence = get_makeup_test_sequence(locked.makeup_test)
        current = sequence[locked.stage - 1] if 1 <= locked.stage <= len(sequence) else None
        if locked.attempt_id != stage.attempt_id or current != (section, module):
            return {'redirect_url': _makeup_redirect_url(locked.makeup_test, locked), 'context': {}}
        canonical = _complete_makeup_answers_from_draft(locked.makeup_test, section, module, draft)
        _submit_makeup_module_locked(locked, section, module, canonical)
        redirect_url = _makeup_redirect_url(locked.makeup_test, locked)
    return {'redirect_url': redirect_url, 'context': {}}


def _regular_module_redirect_url(test_obj, stage, classroom=None):
    current_step = get_current_test_step(stage)
    if current_step is None:
        return _results_url_for_test(test_obj, classroom=classroom)
    if classroom:
        return reverse('classroom_test', kwargs={
            'classroom_id': classroom.id,
            'pk': test_obj.name,
        })
    return reverse('test', kwargs={'pk': test_obj.name})


def _ensure_regular_module_draft(stage, section, module, classroom=None):
    duration_seconds = _module_duration_seconds(stage.user, section)
    draft, created = TestModuleDraft.objects.get_or_create(
        user=stage.user,
        test=stage.test,
        classroom=classroom,
        attempt_id=stage.attempt_id,
        section=_normalize_test_section(section),
        module=_normalize_test_module(module),
        defaults={
            'deadline_at': timezone.now() + timedelta(seconds=duration_seconds),
        },
    )
    if not draft.deadline_at:
        draft.deadline_at = timezone.now() + timedelta(seconds=duration_seconds)
        draft.save(update_fields=['deadline_at', 'updated_at'])
    return draft


def _draft_remaining_seconds(draft):
    return max(int((draft.deadline_at - timezone.now()).total_seconds()), 0)


def _draft_state_payload(draft, questions):
    question_ids = [question.id for question in questions]
    answer_lookup = {
        int(item.get('questionID')): item
        for item in (draft.answers or [])
        if isinstance(item, dict) and str(item.get('questionID', '')).isdigit()
    }
    answers = []
    time_spent = []
    for question_id in question_ids:
        item = answer_lookup.get(question_id, {})
        answers.append(item.get('answer'))
        try:
            time_spent.append(max(int(item.get('time_spent', 0) or 0), 0))
        except (TypeError, ValueError):
            time_spent.append(0)

    def normalize_nested(value):
        if not isinstance(value, list):
            return [[] for _ in question_ids]
        rows = []
        for item in value[:len(question_ids)]:
            rows.append(item if isinstance(item, list) else [])
        rows.extend([[] for _ in range(len(question_ids) - len(rows))])
        return rows

    def normalize_flags(value):
        if not isinstance(value, list):
            return [False for _ in question_ids]
        flags = [bool(item) for item in value[:len(question_ids)]]
        flags.extend([False for _ in range(len(question_ids) - len(flags))])
        return flags

    return {
        'answers': answers,
        'timeSpent': time_spent,
        'eliminatedChoices': normalize_nested(draft.eliminated_choices),
        'markedForReview': normalize_flags(draft.marked_for_review),
        'currentQuestionIndex': min(
            max(int(draft.current_question_index or 0), 0),
            max(len(question_ids) - 1, 0),
        ),
        'deadlineAt': int(draft.deadline_at.timestamp() * 1000),
        'updatedAt': int((draft.updated_at or draft.created_at or timezone.now()).timestamp() * 1000),
    }


def _complete_answers_from_draft(test_obj, section, module, draft):
    questions = list(_module_questions_queryset(test_obj, section, module) or [])
    lookup = {
        int(item.get('questionID')): item
        for item in (draft.answers or [])
        if isinstance(item, dict) and str(item.get('questionID', '')).isdigit()
    }
    completed = []
    for question in questions:
        item = lookup.get(question.id, {})
        completed.append({
            'questionID': question.id,
            'answer': item.get('answer'),
            'time_spent': max(int(item.get('time_spent', 0) or 0), 0),
        })
    return completed



def _regular_module_runtime(stage, section, module, questions, classroom=None):
    """Return render state or a redirect URL when the server timer expired."""
    draft = _ensure_regular_module_draft(stage, section, module, classroom=classroom)
    if _draft_remaining_seconds(draft) > 0:
        return {
            'draft': draft,
            'redirect_url': None,
            'context': {
                'attempt_id': stage.attempt_id,
                'time_remaining_seconds': _draft_remaining_seconds(draft),
                'test_session_state': _draft_state_payload(draft, list(questions)),
                'draft_save_url': reverse('save_test_module_draft'),
            },
        }

    with transaction.atomic():
        locked_stage = TestStage.objects.select_for_update().get(pk=stage.pk)
        if locked_stage.attempt_id != stage.attempt_id or get_current_test_step(locked_stage) != (section, module):
            return {
                'draft': draft,
                'redirect_url': _regular_module_redirect_url(locked_stage.test, locked_stage, classroom),
                'context': {},
            }
        canonical_answers = _complete_answers_from_draft(
            locked_stage.test, section, module, draft
        )
        _submit_regular_module_locked(
            locked_stage,
            locked_stage.test,
            classroom,
            section,
            module,
            canonical_answers,
        )
        redirect_url = _regular_module_redirect_url(locked_stage.test, locked_stage, classroom)

    return {'draft': draft, 'redirect_url': redirect_url, 'context': {}}

def _submit_regular_module_locked(stage, test_obj, classroom, section, module, canonical_answers):
    """Idempotently submit a module while the caller holds a stage row lock."""
    existing = TestModule.objects.filter(
        user=stage.user,
        test=test_obj,
        classroom=classroom,
        test_type='regular',
        section=section,
        module=module,
        attempt_id=stage.attempt_id,
    ).first()
    if existing:
        return existing, False

    module_obj = TestModule.objects.create(
        user=stage.user,
        test=test_obj,
        classroom=classroom,
        test_type='regular',
        section=section,
        module=module,
        attempt_id=stage.attempt_id,
        answers=json.dumps({'answers': canonical_answers}),
    )
    TestModuleDraft.objects.filter(
        user=stage.user,
        test=test_obj,
        attempt_id=stage.attempt_id,
        section=section,
        module=module,
    ).delete()
    advance_test_stage(stage)
    return module_obj, True


def _required_modules_for_test(test_obj):
    return get_test_sequence(test_obj)


def _section_submission_status(required_modules, missing_modules):
    """Return completion flags for only the modules a test actually contains.

    Older result views hard-coded m1+m2 for both sections. That marked a legitimate
    one-module test as incomplete even when every required module was submitted.
    """
    required = {
        (_normalize_test_section(section), _normalize_test_module(module))
        for section, module in (required_modules or [])
    }
    missing = {
        tuple(str(item).split('_', 1))
        for item in (missing_modules or [])
        if '_' in str(item)
    }

    def complete(section):
        slots = {slot for slot in required if slot[0] == section}
        return bool(slots) and not any(slot in missing for slot in slots)

    return {
        'english': complete('english'),
        'math': complete('math'),
        'total': bool(required) and not missing,
    }


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




def _classroom_id_value(classroom):
    if not classroom:
        return None
    if hasattr(classroom, 'id'):
        return classroom.id
    try:
        return int(classroom)
    except (TypeError, ValueError):
        return None


def _classroom_scope_filter(classroom):
    """Always scope SAT attempts.

    classroom=None means regular/non-classroom attempts only. A concrete
    classroom means attempts for that classroom only. This prevents a test solved
    in one teacher's classroom from blocking the same test in another classroom.
    """
    return {'classroom_id': _classroom_id_value(classroom)}


def _get_classroom_context_from_id(user, classroom_id, test_obj=None):
    if not classroom_id:
        return None

    try:
        classroom_id = int(classroom_id)
    except (TypeError, ValueError):
        raise Http404("Invalid classroom id.")

    classroom = get_object_or_404(Classroom, id=classroom_id, is_active=True)

    if user.is_superuser or user.is_staff or is_member(user, ['Admin', 'Tester']) or classroom.teacher_id == user.id:
        return classroom

    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=user,
        role='student',
        status='approved',
    ).first()

    if not membership:
        raise Http404("Classroom access was not found.")

    if not get_membership_section_access_map(membership).get('practice_tests'):
        raise Http404("Practice Tests access was not granted for this classroom.")

    if test_obj is not None:
        allowed = StudentPracticeTestAccess.objects.filter(
            membership=membership,
            test=test_obj,
            has_access=True,
        ).exists()
        if not allowed:
            raise Http404("This test is not assigned in this classroom.")

    return classroom


def _results_url_for_test(test_obj, classroom=None, review_key=None):
    base_url = reverse('results', kwargs={'test': test_obj.name})
    params = []
    if review_key:
        params.append(f"review_key={review_key}")
    classroom_id = _classroom_id_value(classroom)
    if classroom_id:
        params.append(f"classroom_id={classroom_id}")
    return f"{base_url}?{'&'.join(params)}" if params else base_url

def _safe_answers_list(raw_answers):
    try:
        payload = json.loads(raw_answers or '{}')
    except Exception:
        return []

    answers = payload.get('answers', [])
    return answers if isinstance(answers, list) else []



def _review_results_url(review, classroom=None, student=None):
    if not review or not review.test:
        return ''

    if classroom is not None and student is not None:
        base_url = reverse(
            'classroom_student_review_results',
            args=[classroom.id, student.id, review.test.name]
        )
        return f"{base_url}?review_key={review.key}"

    return _results_url_for_test(review.test, classroom=classroom or review.classroom, review_key=review.key)


def _module_contains_question(module_obj, question_id):
    target_id = str(question_id)
    for item in _safe_answers_list(module_obj.answers):
        if str(item.get('questionID', '')) == target_id:
            return True
    return False


def _review_question_url(review, section, module, question_id, classroom=None, student=None):
    if not review:
        return ''

    module_obj = TestModule.objects.filter(
        test=review.test,
        user=review.user,
        section=section,
        module=module,
        attempt_id=review.attempt_id,
        classroom_id=review.classroom_id,
    ).first()

    if not module_obj or not _module_contains_question(module_obj, question_id):
        return _review_results_url(review, classroom=classroom, student=student)

    if classroom is not None and student is not None:
        return reverse(
            'classroom_student_review_question',
            args=[classroom.id, student.id, review.key, section, module, question_id]
        )

    return reverse('question', args=[review.key, section, module, question_id])


def _build_review_attempt_options(attempts, selected_review=None, *, section=None, module=None, question_id=None, classroom=None, student=None):
    total = len(attempts)
    options = []

    for index, attempt in enumerate(attempts):
        attempt_number = total - index
        created_at = timezone.localtime(attempt.created_at).strftime('%Y-%m-%d %H:%M') if attempt.created_at else ''
        score = attempt.score if attempt.score is not None else '—'
        label = f"Attempt {attempt_number} · {created_at} · Score: {score}"

        if section and module and question_id:
            url = _review_question_url(
                attempt,
                section,
                module,
                question_id,
                classroom=classroom,
                student=student,
            )
        else:
            url = _review_results_url(attempt, classroom=classroom, student=student)

        options.append({
            'key': attempt.key,
            'label': label,
            'url': url,
            'selected': bool(selected_review and attempt.key == selected_review.key),
        })

    return options

def _resolve_attempt_id(user, test_obj, selected_review=None, classroom=None):
    if selected_review and selected_review.attempt_id:
        return selected_review.attempt_id

    latest_stage = _latest_regular_test_stage(user, test_obj, classroom=classroom)
    if latest_stage and latest_stage.attempt_id:
        return latest_stage.attempt_id

    latest_scored_review = TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at').first()
    if latest_scored_review and latest_scored_review.attempt_id:
        return latest_scored_review.attempt_id

    latest_module = TestModule.objects.filter(user=user, test=test_obj, **_classroom_scope_filter(classroom)).order_by('-created_at').first()
    if latest_module and latest_module.attempt_id:
        return latest_module.attempt_id

    return None


def _load_latest_modules(user, test_obj, attempt_id=None, classroom=None):
    latest_modules = {}
    queryset = TestModule.objects.filter(user=user, test=test_obj, **_classroom_scope_filter(classroom))

    if attempt_id:
        queryset = queryset.filter(attempt_id=attempt_id)

    for module in queryset.order_by('-created_at'):
        key = f"{module.section}_{module.module}"
        if key not in latest_modules:
            latest_modules[key] = module

    if latest_modules or attempt_id:
        return latest_modules

    for module in TestModule.objects.filter(user=user, test=test_obj, **_classroom_scope_filter(classroom)).order_by('-created_at'):
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


def _calculate_attempt_score(user, test_obj, attempt_id, classroom=None):
    if not attempt_id:
        return None

    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return None

    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id, classroom=classroom)
    modules_to_process = []
    for section, module in required_modules:
        module_obj = latest_modules.get(f"{section}_{module}")
        if not module_obj:
            return None
        modules_to_process.append(module_obj)

    correct_counts = {
        'english': {'m1': 0, 'm2': 0},
        'math': {'m1': 0, 'm2': 0},
    }
    english_question_map, math_question_map = _build_question_maps(modules_to_process)

    for module_obj in modules_to_process:
        sec = _normalize_test_section(module_obj.section)
        mod = _normalize_test_module(module_obj.module)
        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in _safe_answers_list(module_obj.answers):
            try:
                question_id = int(answer['questionID'])
            except (KeyError, TypeError, ValueError):
                continue

            if sec == 'english':
                question = english_question_map.get(question_id)
                is_correct = bool(question and check_english_answer(question, answer.get('answer')))
            else:
                question = math_question_map.get(question_id)
                raw_answer = answer.get('answer')
                is_correct = bool(question and raw_answer is not None and check_written(raw_answer, question.answer))

            if is_correct:
                correct_counts[sec][mod] += 1

    return _score_from_counts(get_test_mode(test_obj), correct_counts)


def _completed_attempt_ids_from_modules(user, test_obj, classroom=None):
    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return []

    required_slots = {
        (_normalize_test_section(section), _normalize_test_module(module))
        for section, module in required_modules
    }
    slots_by_attempt = defaultdict(set)
    latest_time_by_attempt = {}

    modules = TestModule.objects.filter(
        user=user,
        test=test_obj,
        test_type='regular',
        attempt_id__isnull=False,
        **_classroom_scope_filter(classroom),
    ).only('attempt_id', 'section', 'module', 'created_at', 'created')

    for module_obj in modules:
        attempt_id = module_obj.attempt_id
        if not attempt_id:
            continue

        slot = (
            _normalize_test_section(module_obj.section),
            _normalize_test_module(module_obj.module),
        )
        slots_by_attempt[attempt_id].add(slot)

        module_time = module_obj.created_at or module_obj.created
        if module_time and (
            attempt_id not in latest_time_by_attempt or
            module_time > latest_time_by_attempt[attempt_id]
        ):
            latest_time_by_attempt[attempt_id] = module_time

    fallback_time = timezone.now() - timedelta(days=36500)
    completed_attempt_ids = [
        attempt_id
        for attempt_id, slots in slots_by_attempt.items()
        if required_slots.issubset(slots)
    ]
    completed_attempt_ids.sort(
        key=lambda attempt_id: latest_time_by_attempt.get(attempt_id) or fallback_time,
        reverse=True,
    )
    return completed_attempt_ids


def _ensure_scored_review_for_attempt(user, test_obj, attempt_id, classroom=None):
    if not attempt_id:
        return None

    existing_scored = TestReview.objects.filter(
        user=user,
        test=test_obj,
        attempt_id=attempt_id,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at').first()
    if existing_scored:
        if not existing_scored.key:
            existing_scored.update_key()
        return existing_scored

    score = _calculate_attempt_score(user, test_obj, attempt_id, classroom=classroom)
    if not score:
        return None

    review = TestReview.objects.filter(
        user=user,
        test=test_obj,
        attempt_id=attempt_id,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at').first()

    if not review:
        review = TestReview.objects.create(
            user=user,
            test=test_obj,
            classroom=classroom,
            attempt_id=attempt_id,
        )
        review.update_key()
    elif not review.key:
        review.update_key()

    latest_module = TestModule.objects.filter(
        user=user,
        test=test_obj,
        test_type='regular',
        attempt_id=attempt_id,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at', '-created').first()
    latest_module_time = None
    if latest_module:
        latest_module_time = latest_module.created_at or latest_module.created

    review.score = score.get('total', 0) if isinstance(score, dict) else 0
    update_fields = ['score']

    if latest_module_time:
        review.created_at = latest_module_time
        update_fields.append('created_at')

    if user.groups.filter(name='OFFLINE').exists():
        review.duration = timedelta(days=3)
        update_fields.append('duration')

    review.save(update_fields=update_fields)
    return review


def _backfill_completed_attempt_reviews(user, test_obj, classroom=None):
    """Create missing TestReview rows for completed attempts saved as modules.

    This repairs attempts completed while the old results view kept selecting the
    previous review. Without this, a student could retake a test, finish all
    modules, and still see only Attempt 1 in the dropdown.
    """
    for attempt_id in _completed_attempt_ids_from_modules(user, test_obj, classroom=classroom):
        _ensure_scored_review_for_attempt(user, test_obj, attempt_id, classroom=classroom)


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


def _latest_regular_test_stage(user, test_obj, classroom=None):
    return TestStage.objects.filter(
        user=user,
        test=test_obj,
        test_type='regular',
        **_classroom_scope_filter(classroom),
    ).order_by('-updated_at', '-created_at', '-id').first()


def _get_or_create_regular_test_stage(user, test_obj, *, stage=1, classroom=None):
    existing_stage = _latest_regular_test_stage(user, test_obj, classroom=classroom)
    if existing_stage:
        return existing_stage, False

    return TestStage.objects.create(
        user=user,
        test=test_obj,
        classroom=classroom,
        test_type='regular',
        stage=stage,
    ), True


def _attempt_module_slots(user, test_obj, attempt_id, classroom=None):
    if not attempt_id:
        return set()

    slots = set()
    for section, module in TestModule.objects.filter(
        user=user,
        test=test_obj,
        test_type='regular',
        attempt_id=attempt_id,
        **_classroom_scope_filter(classroom),
    ).values_list('section', 'module'):
        slots.add((
            _normalize_test_section(section),
            _normalize_test_module(module),
        ))
    return slots


def _attempt_has_scored_review(user, test_obj, attempt_id, classroom=None):
    if not attempt_id:
        return False

    return TestReview.objects.filter(
        user=user,
        test=test_obj,
        attempt_id=attempt_id,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).exists()


def _stage_attempt_is_complete(stage):
    if not stage or not stage.test_id:
        return False

    sequence = get_test_sequence(stage.test)
    if not sequence:
        return False

    if stage.stage > len(sequence):
        return True

    required_slots = {
        (_normalize_test_section(section), _normalize_test_module(module))
        for section, module in sequence
    }
    submitted_slots = _attempt_module_slots(stage.user, stage.test, stage.attempt_id, classroom=stage.classroom)

    return bool(required_slots and required_slots.issubset(submitted_slots))


def _get_resumable_stage(user, test_obj, classroom=None):
    stage = _latest_regular_test_stage(user, test_obj, classroom=classroom)

    if not stage:
        return None

    if _attempt_has_scored_review(user, test_obj, stage.attempt_id, classroom=classroom):
        return None

    if _stage_attempt_is_complete(stage):
        return None

    return stage


def _has_resumable_test_attempt(user, test_obj, classroom=None):
    return _get_resumable_stage(user, test_obj, classroom=classroom) is not None


def _split_tests_by_user_progress(user, tests, classroom=None):
    """Return decorated active/past practice-test lists without per-card queries.

    The old implementation performed several database queries for every test card.
    Besides being slow, it could not explain whether a card represented a fresh
    start, a resumable attempt, or a completed attempt waiting for its result.
    This version batches reviews, stages, submitted modules, and question counts,
    then attaches template-only metadata to every ``Test`` object.
    """
    tests = list(tests)
    if not tests:
        return [], []

    test_ids = [test.pk for test in tests]
    scope_filter = _classroom_scope_filter(classroom)

    reviews = TestReview.objects.filter(
        user=user,
        test_id__in=test_ids,
        score__isnull=False,
        **scope_filter,
    ).order_by('test_id', '-created_at', '-id')
    latest_reviews = _latest_by_test_id(reviews)

    stages = TestStage.objects.filter(
        user=user,
        test_id__in=test_ids,
        test_type='regular',
        **scope_filter,
    ).order_by('test_id', '-updated_at', '-created_at', '-id')
    latest_stages = _latest_by_test_id(stages)

    english_rows = list(
        English_Question.objects.filter(test_id__in=test_ids)
        .values('test_id', 'module')
        .annotate(total=Count('id'))
    )
    math_rows = list(
        Math_Question.objects.filter(test_id__in=test_ids)
        .values('test_id', 'module')
        .annotate(total=Count('id'))
    )

    question_counts = defaultdict(lambda: {'english': 0, 'math': 0})
    required_slots = defaultdict(set)

    for row in english_rows:
        test_id = row['test_id']
        question_counts[test_id]['english'] += row['total']
        required_slots[test_id].add(('english', _normalize_test_module(row['module'])))

    for row in math_rows:
        test_id = row['test_id']
        question_counts[test_id]['math'] += row['total']
        required_slots[test_id].add(('math', _normalize_test_module(row['module'])))

    stage_attempt_ids = [
        stage.attempt_id for stage in latest_stages.values() if stage and stage.attempt_id
    ]
    reviewed_attempt_ids = set()
    submitted_slots = defaultdict(set)

    if stage_attempt_ids:
        reviewed_attempt_ids = set(
            TestReview.objects.filter(
                user=user,
                attempt_id__in=stage_attempt_ids,
                score__isnull=False,
                **scope_filter,
            ).values_list('attempt_id', flat=True)
        )

        for test_id, attempt_id, section, module in TestModule.objects.filter(
            user=user,
            test_id__in=test_ids,
            attempt_id__in=stage_attempt_ids,
            test_type='regular',
            **scope_filter,
        ).values_list('test_id', 'attempt_id', 'section', 'module'):
            submitted_slots[(test_id, attempt_id)].add((
                _normalize_test_section(section),
                _normalize_test_module(module),
            ))

    active_tests = []
    past_tests = []

    for test in tests:
        review = latest_reviews.get(test.pk)
        stage = latest_stages.get(test.pk)
        required = required_slots.get(test.pk, set())
        submitted = submitted_slots.get((test.pk, getattr(stage, 'attempt_id', None)), set())
        total_modules = len(required)
        completed_modules = len(required.intersection(submitted)) if required else 0

        stage_complete = False
        if stage and required:
            stage_complete = (
                stage.stage > total_modules
                or required.issubset(submitted)
            )

        stage_has_review = bool(
            stage and stage.attempt_id in reviewed_attempt_ids
        )
        has_resumable_attempt = bool(
            stage and required and not stage_has_review and not stage_complete
        )

        # A stage may already have advanced even when a legacy module row is
        # missing. Use the larger value only for visual progress, never for
        # completion decisions.
        if stage and total_modules:
            completed_modules = max(
                completed_modules,
                min(max(stage.stage - 1, 0), total_modules),
            )

        english_total = question_counts[test.pk]['english']
        math_total = question_counts[test.pk]['math']
        question_total = english_total + math_total

        if english_total and math_total:
            mode_label = 'Full SAT'
        elif english_total:
            mode_label = 'Reading & Writing'
        elif math_total:
            mode_label = 'Math'
        else:
            mode_label = 'No questions'

        progress_percent = (
            round((completed_modules / total_modules) * 100)
            if total_modules else 0
        )

        # Dynamic attributes are intentionally consumed only by templates.
        test.latest_review = review
        test.latest_review_key = review.key if review and review.key else ''
        test.latest_score = review.score if review else None
        test.latest_review_date = review.created_at if review else None
        test.has_completed_attempt = bool(review)
        test.has_active_attempt = has_resumable_attempt
        test.stage_complete_without_review = bool(stage and stage_complete and not review)
        test.question_count = question_total
        test.english_question_count = english_total
        test.math_question_count = math_total
        test.module_count = total_modules
        test.completed_modules = completed_modules
        test.progress_percent = progress_percent
        test.mode_label = mode_label
        test.card_image = _resolve_test_card_image(test)
        test.current_module_number = (
            min(max(stage.stage, 1), total_modules) if stage and total_modules else None
        )

        if not question_total:
            test.card_state = 'unavailable'
            test.action_label = 'Unavailable'
            test.status_label = 'No questions'
        elif has_resumable_attempt:
            test.card_state = 'continue'
            test.action_label = 'Continue test'
            test.status_label = 'In progress'
        elif stage and stage_complete and not review:
            test.card_state = 'finalizing'
            test.action_label = 'Open result'
            test.status_label = 'Finishing'
        else:
            test.card_state = 'start'
            test.action_label = 'Start test'
            test.status_label = 'Ready'

        if review:
            past_tests.append(test)

        if not review or has_resumable_attempt:
            active_tests.append(test)

    return active_tests, past_tests


DEFAULT_TEST_CARD_IMAGE = 'assets/img/tests/minion.jpg'


def _resolve_test_card_image(test):
    """Pick the numbered card image for a test, falling back to the default.

    Under ManifestStaticFilesStorage an unknown path raises ValueError, so the
    lookup has to happen here rather than in the template.
    """
    if getattr(test, 'icon', None):
        try:
            return test.icon.url
        except ValueError:
            pass

    name = str(test.name or '')
    for token in ('Day', 'DAY', 'day', ' '):
        name = name.replace(token, '')

    if name.isdigit() and len(name) <= 2:
        try:
            return static_url('assets/img/tests/%s.png' % name)
        except ValueError:
            pass

    return static_url(DEFAULT_TEST_CARD_IMAGE)


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
        'practice_summary': {
            'available': len(tests),
            'active': len(active_tests),
            'past': len(past_tests),
            'resumable': sum(1 for test in active_tests if test.has_active_attempt),
        },
        'show_lessons': True,
    }
    context.update(lessons_context)

    return render(request, 'sat/practice_tests.html', context)

@login_required(login_url='/login/')
@require_POST
def save_test_module_draft(request):
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    test_name = payload.get('test')
    section = _normalize_test_section(payload.get('section'))
    module = _normalize_test_module(payload.get('module'))
    attempt_id = payload.get('attempt_id') or payload.get('attemptId')
    if not test_name or section not in {'english', 'math'} or module not in {'m1', 'm2'} or not attempt_id:
        return JsonResponse({'ok': False, 'error': 'test, attempt_id, section, and module are required.'}, status=400)

    try:
        attempt_id = uuid.UUID(str(attempt_id))
    except (TypeError, ValueError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Invalid attempt_id.'}, status=400)

    test_type = payload.get('test_type') or payload.get('testType') or 'regular'
    if test_type == 'makeup':
        makeup_test = get_object_or_404(MakeupTest, name=test_name)
        if not makeup_test.groups.filter(id__in=request.user.groups.values_list('id', flat=True)).exists():
            return JsonResponse({'ok': False, 'error': 'You do not have access to this makeup test.'}, status=403)
        with transaction.atomic():
            stage = TestStage.objects.select_for_update().filter(
                user=request.user,
                makeup_test=makeup_test,
                test_type='makeup',
            ).order_by('-updated_at', '-created_at', '-id').first()
            if not stage or stage.attempt_id != attempt_id:
                return JsonResponse({
                    'ok': False,
                    'error': 'This makeup-test tab belongs to an old attempt.',
                    'redirect_url': reverse('makeup_test_module', kwargs={'pk': makeup_test.name}),
                }, status=409)
            sequence = get_makeup_test_sequence(makeup_test)
            current_step = sequence[stage.stage - 1] if 1 <= stage.stage <= len(sequence) else None
            if current_step != (section, module):
                return JsonResponse({
                    'ok': False,
                    'error': 'This makeup module is no longer active.',
                    'redirect_url': _makeup_redirect_url(makeup_test, stage),
                }, status=409)
            is_valid, error, canonical_answers = _canonical_partial_makeup_answers(
                makeup_test, section, module, payload.get('answers') or []
            )
            if not is_valid:
                return JsonResponse({'ok': False, 'error': error}, status=400)
            draft = _ensure_makeup_module_draft(stage, section, module)
            if _draft_remaining_seconds(draft) <= 0:
                return JsonResponse({'ok': False, 'error': 'Time is over for this module.', 'time_over': True}, status=409)
            questions = list(makeup_test.get_module_questions(section, _module_db_name(module)) or [])
            expected_count = len(questions)
            eliminated = payload.get('eliminated_choices', payload.get('eliminatedChoices'))
            if not isinstance(eliminated, list):
                eliminated = [[] for _ in range(expected_count)]
            eliminated = [
                [str(choice).upper() for choice in row if str(choice).upper() in {'A', 'B', 'C', 'D'}]
                if isinstance(row, list) else []
                for row in eliminated[:expected_count]
            ]
            eliminated.extend([[] for _ in range(expected_count - len(eliminated))])
            marked = payload.get('marked_for_review', payload.get('markedForReview'))
            marked = [bool(item) for item in marked[:expected_count]] if isinstance(marked, list) else []
            marked.extend([False for _ in range(expected_count - len(marked))])
            try:
                current_index = int(payload.get('current_question_index', payload.get('currentQuestionIndex', 0)) or 0)
            except (TypeError, ValueError):
                current_index = 0
            draft.answers = canonical_answers
            draft.time_spent = [max(int(item.get('time_spent', 0) or 0), 0) for item in canonical_answers]
            draft.eliminated_choices = eliminated
            draft.marked_for_review = marked
            draft.current_question_index = min(max(current_index, 0), max(expected_count - 1, 0))
            draft.save(update_fields=[
                'answers', 'time_spent', 'eliminated_choices', 'marked_for_review',
                'current_question_index', 'updated_at',
            ])
        return JsonResponse({
            'ok': True,
            'saved': True,
            'remaining_seconds': _draft_remaining_seconds(draft),
            'deadline_at': int(draft.deadline_at.timestamp() * 1000),
            'saved_at': int((draft.updated_at or timezone.now()).timestamp() * 1000),
        })

    test_obj = get_object_or_404(Test, name=test_name)
    classroom = _get_classroom_context_from_id(
        request.user,
        payload.get('classroom_id') or payload.get('classroomId'),
        test_obj=test_obj,
    )
    if classroom is None and not user_has_test_access(request.user, test_obj):
        return JsonResponse({'ok': False, 'error': 'You do not have access to this test.'}, status=403)

    with transaction.atomic():
        stage = TestStage.objects.select_for_update().filter(
            user=request.user,
            test=test_obj,
            classroom=classroom,
            test_type='regular',
        ).order_by('-updated_at', '-created_at', '-id').first()
        if not stage or stage.attempt_id != attempt_id:
            return JsonResponse({
                'ok': False,
                'error': 'This test tab belongs to an old attempt.',
                'redirect_url': _regular_module_redirect_url(test_obj, stage, classroom) if stage else _results_url_for_test(test_obj, classroom=classroom),
            }, status=409)

        current_step = get_current_test_step(stage)
        if current_step != (section, module):
            return JsonResponse({
                'ok': False,
                'error': 'This module is no longer active.',
                'redirect_url': _regular_module_redirect_url(test_obj, stage, classroom),
            }, status=409)

        is_valid, error, canonical_answers = _canonical_partial_module_answers(
            test_obj, section, module, payload.get('answers') or []
        )
        if not is_valid:
            return JsonResponse({'ok': False, 'error': error}, status=400)

        draft = _ensure_regular_module_draft(stage, section, module, classroom=classroom)
        if _draft_remaining_seconds(draft) <= 0:
            return JsonResponse({
                'ok': False,
                'error': 'Time is over for this module.',
                'time_over': True,
            }, status=409)

        question_queryset = _module_questions_queryset(test_obj, section, module)
        expected_count = question_queryset.count() if question_queryset is not None else 0

        def bounded_list(value, fallback, nested=False):
            if not isinstance(value, list):
                return fallback
            result = value[:expected_count]
            while len(result) < expected_count:
                result.append([] if nested else False)
            return result

        try:
            current_index = int(payload.get('current_question_index', payload.get('currentQuestionIndex', 0)) or 0)
        except (TypeError, ValueError):
            current_index = 0

        draft.answers = canonical_answers
        draft.time_spent = [
            max(int(item.get('time_spent', 0) or 0), 0)
            for item in canonical_answers
        ]
        draft.eliminated_choices = bounded_list(
            payload.get('eliminated_choices', payload.get('eliminatedChoices')),
            [[] for _ in range(expected_count)],
            nested=True,
        )
        draft.marked_for_review = bounded_list(
            payload.get('marked_for_review', payload.get('markedForReview')),
            [False for _ in range(expected_count)],
        )
        draft.current_question_index = min(max(current_index, 0), max(expected_count - 1, 0))
        draft.save(update_fields=[
            'answers', 'time_spent', 'eliminated_choices', 'marked_for_review',
            'current_question_index', 'updated_at',
        ])

    return JsonResponse({
        'ok': True,
        'saved': True,
        'remaining_seconds': _draft_remaining_seconds(draft),
        'deadline_at': int(draft.deadline_at.timestamp() * 1000),
        'saved_at': int((draft.updated_at or timezone.now()).timestamp() * 1000),
    })


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
            makeup_test_obj = MakeupTest.objects.filter(name=test_name).first()
            if not makeup_test_obj:
                return JsonResponse({'ok': False, 'error': 'Makeup test not found.'}, status=404)
            if not makeup_test_obj.groups.filter(id__in=request.user.groups.values_list('id', flat=True)).exists():
                return JsonResponse({'ok': False, 'error': 'You do not have access to this makeup test.'}, status=403)

            section = _normalize_test_section(section)
            module = _normalize_test_module(module)
            payload_attempt_id = payload.get('attempt_id') or payload.get('attemptId')
            try:
                payload_attempt_id = uuid.UUID(str(payload_attempt_id))
            except (TypeError, ValueError, AttributeError):
                return JsonResponse({'ok': False, 'error': 'Valid attempt_id is required.'}, status=400)

            is_valid, validation_error, canonical_answers = _validate_makeup_module_answers(
                makeup_test_obj, section, module, answers
            )
            if not is_valid:
                return JsonResponse({'ok': False, 'error': validation_error}, status=400)

            with transaction.atomic():
                test_stage = TestStage.objects.select_for_update().filter(
                    user=request.user,
                    makeup_test=makeup_test_obj,
                    test_type='makeup',
                ).order_by('-updated_at', '-created_at', '-id').first()
                if not test_stage or test_stage.attempt_id != payload_attempt_id:
                    return JsonResponse({
                        'ok': False,
                        'error': 'This makeup-test tab belongs to an old attempt.',
                        'redirect_url': reverse('makeup_test_module', kwargs={'pk': makeup_test_obj.name}),
                    }, status=409)

                sequence = get_makeup_test_sequence(makeup_test_obj)
                current_step = (
                    sequence[test_stage.stage - 1]
                    if 1 <= test_stage.stage <= len(sequence)
                    else None
                )
                existing_module = TestModule.objects.filter(
                    user=request.user,
                    makeup_test=makeup_test_obj,
                    test_type='makeup',
                    section=section,
                    module=module,
                    attempt_id=test_stage.attempt_id,
                ).first()
                if existing_module:
                    redirect_url = (
                        reverse('makeup_test_module', kwargs={'pk': makeup_test_obj.name})
                        if current_step is not None
                        else reverse('sat_menu')
                    )
                    return JsonResponse({
                        'ok': True,
                        'saved': True,
                        'already_submitted': True,
                        'redirect_url': redirect_url,
                    })

                if current_step != (section, module):
                    return JsonResponse({
                        'ok': False,
                        'error': 'This makeup module is no longer active.',
                        'redirect_url': reverse('makeup_test_module', kwargs={'pk': makeup_test_obj.name}),
                    }, status=409)

                active_draft = MakeupTestModuleDraft.objects.select_for_update().filter(
                    user=request.user,
                    makeup_test=makeup_test_obj,
                    attempt_id=test_stage.attempt_id,
                    section=section,
                    module=module,
                ).first()
                if not active_draft:
                    return JsonResponse({
                        'ok': False,
                        'error': 'Open the active makeup module before submitting it.',
                        'redirect_url': reverse('makeup_test_module', kwargs={'pk': makeup_test_obj.name}),
                    }, status=409)
                submitted_after_deadline = active_draft.deadline_at <= timezone.now()
                if submitted_after_deadline:
                    canonical_answers = _complete_makeup_answers_from_draft(
                        makeup_test_obj, section, module, active_draft
                    )
                _submit_makeup_module_locked(
                    test_stage, section, module, canonical_answers
                )
                redirect_url = _makeup_redirect_url(makeup_test_obj, test_stage)

            return JsonResponse({
                'ok': True,
                'saved': True,
                'section': section,
                'module': module,
                'test': test_name,
                'test_type': 'makeup',
                'redirect_url': redirect_url,
                'submitted_after_deadline': submitted_after_deadline,
            })

        try:
            test_obj = Test.objects.get(name=test_name)
        except Test.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Test not found.'}, status=404)

        classroom = _get_classroom_context_from_id(
            request.user,
            payload.get('classroom_id') or payload.get('classroomId'),
            test_obj=test_obj,
        )

        if classroom is None and not user_has_test_access(request.user, test_obj):
            return JsonResponse({'ok': False, 'error': 'You do not have access to this test.'}, status=403)

        section = _normalize_test_section(section)
        module = _normalize_test_module(module)
        payload_attempt_id = payload.get('attempt_id') or payload.get('attemptId')
        if not payload_attempt_id:
            return JsonResponse({
                'ok': False,
                'error': 'attempt_id is required for a timed module submission.',
            }, status=400)
        try:
            payload_attempt_id = uuid.UUID(str(payload_attempt_id))
        except (TypeError, ValueError, AttributeError):
            return JsonResponse({'ok': False, 'error': 'Invalid attempt_id.'}, status=400)

        is_valid, validation_error, canonical_answers = _validate_regular_module_answers(test_obj, section, module, answers)
        if not is_valid:
            return JsonResponse({'ok': False, 'error': validation_error}, status=400)

        with transaction.atomic():
            test_stage = TestStage.objects.select_for_update().filter(
                user=request.user,
                test=test_obj,
                classroom=classroom,
                test_type='regular',
            ).order_by('-updated_at', '-created_at', '-id').first()
            if not test_stage:
                test_stage = TestStage.objects.create(
                    user=request.user,
                    test=test_obj,
                    classroom=classroom,
                    test_type='regular',
                    stage=1,
                )

            if payload_attempt_id and test_stage.attempt_id != payload_attempt_id:
                return JsonResponse({
                    'ok': False,
                    'error': 'This test tab belongs to an old attempt.',
                    'redirect_url': _regular_module_redirect_url(test_obj, test_stage, classroom),
                }, status=409)

            current_step = get_current_test_step(test_stage)
            existing_module = TestModule.objects.filter(
                user=request.user,
                test=test_obj,
                classroom=classroom,
                test_type='regular',
                section=section,
                module=module,
                attempt_id=test_stage.attempt_id,
            ).first()

            # Idempotency: a retry after a successful submit must never advance twice.
            if existing_module:
                redirect_url = _regular_module_redirect_url(test_obj, test_stage, classroom)
                return JsonResponse({
                    'ok': True,
                    'saved': True,
                    'already_submitted': True,
                    'redirect_url': redirect_url,
                })

            if current_step != (section, module):
                expected = f"{current_step[0]} / {current_step[1]}" if current_step else 'finished'
                return JsonResponse({
                    'ok': False,
                    'error': f'Invalid module order. Expected {expected}.',
                    'redirect_url': _regular_module_redirect_url(test_obj, test_stage, classroom),
                }, status=409)

            # A regular timed module must have been opened/saved first so the
            # server has an authoritative start time. Without this check a forged
            # direct POST could submit a module without ever starting its timer.
            active_draft = TestModuleDraft.objects.filter(
                user=request.user,
                test=test_obj,
                classroom=classroom,
                attempt_id=test_stage.attempt_id,
                section=section,
                module=module,
            ).first()
            if not active_draft:
                return JsonResponse({
                    'ok': False,
                    'error': 'Open the active module before submitting it.',
                    'redirect_url': _regular_module_redirect_url(test_obj, test_stage, classroom),
                }, status=409)

            # The deadline is server-authoritative. A forged or delayed request may
            # not change answers after time expires; in that case submit the last
            # server draft exactly as it stood when time ran out.
            submitted_after_deadline = active_draft.deadline_at <= timezone.now()
            if submitted_after_deadline:
                canonical_answers = _complete_answers_from_draft(
                    test_obj, section, module, active_draft
                )

            _submit_regular_module_locked(
                test_stage,
                test_obj,
                classroom,
                section,
                module,
                canonical_answers,
            )
            redirect_url = _regular_module_redirect_url(test_obj, test_stage, classroom)

        return JsonResponse({
            'ok': True,
            'saved': True,
            'section': section,
            'module': module,
            'test': test_name,
            'test_type': 'regular',
            'classroom_id': classroom.id if classroom else None,
            'redirect_url': redirect_url,
            'submitted_after_deadline': submitted_after_deadline,
        })

    # ---------- CASE 2: single answer check ----------
    # Never reveal correctness during a live SAT attempt. The old endpoint made it
    # possible to script-check every option before submitting a module.
    if not (request.user.is_staff or request.user.is_superuser or is_member(request.user, ['Admin', 'Tester'])):
        return JsonResponse({
            'ok': False,
            'error': 'Single-answer checking is disabled during SAT tests.',
        }, status=403)

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
        is_correct = check_english_answer(question, answer)
    else:
        is_correct = check_written(answer, question.answer)

    return JsonResponse({
        'ok': True,
        'questionID': question_id,
        'is_correct': is_correct,
        'correct_answer': None,
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
    classroom = _get_classroom_context_from_id(
        user,
        request.GET.get('classroom_id') or request.GET.get('classroom'),
        test_obj=test_obj,
    )

    _backfill_completed_attempt_reviews(user, test_obj, classroom=classroom)

    review_key = request.GET.get('review_key')
    attempts = list(TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at'))
    selected_review = None

    # Do not automatically select the latest review when review_key is absent.
    # A fresh retake finishes by opening /results/<test> without review_key;
    # in that case we must score the current scoped TestStage.attempt_id.
    if review_key:
        selected_review = next((rev for rev in attempts if rev.key == review_key), None)
        if not selected_review:
            return HttpResponse("Selected attempt was not found.", status=404)

    test_mode = get_test_mode(test_obj)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    required_modules = _required_modules_for_test(test_obj)
    if not required_modules:
        return HttpResponse("Questions are not found", status=404)

    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review, classroom=classroom)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id, classroom=classroom)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    if missing_modules:
        messages.warning(request, "Finish the active module before opening results.")
        stage = _get_resumable_stage(user, test_obj, classroom=classroom)
        if stage:
            if classroom:
                return redirect('classroom_test', classroom_id=classroom.id, pk=test_obj.name)
            return redirect('test', pk=test_obj.name)
        return HttpResponse("The attempt is incomplete and cannot be scored yet.", status=409)

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
                    is_correct = bool(q_obj and check_english_answer(q_obj, answer.get('answer')))
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

    current_stage = _latest_regular_test_stage(user, test_obj, classroom=classroom)
    current_attempt_id = attempt_id or (current_stage.attempt_id if current_stage else None)

    if selected_review and selected_review.attempt_id:
        testreview = selected_review
    else:
        testreview = None
        if current_attempt_id:
            testreview = TestReview.objects.filter(
                user=user,
                test=test_obj,
                attempt_id=current_attempt_id,
                **_classroom_scope_filter(classroom),
            ).order_by('-created_at').first()

        if not testreview:
            testreview = TestReview.objects.create(
                user=user,
                test=test_obj,
                classroom=classroom,
                attempt_id=current_attempt_id or uuid.uuid4()
            )
            testreview.update_key()
            if user.groups.filter(name='OFFLINE').exists():
                testreview.duration = timedelta(days=3)
                testreview.save(update_fields=['duration'])

    if not review_key:
        testreview.score = score['total'] if isinstance(score, dict) else 0
        testreview.save(update_fields=['score'])
        if classroom:
            recalculate_practice_tests_progress(classroom, user)

    key = testreview.key
    selected_review = testreview

    attempts = list(TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at'))
    if selected_review:
        selected_review = next((attempt for attempt in attempts if attempt.key == selected_review.key), selected_review)

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
        'attempt_options': _build_review_attempt_options(attempts, selected_review, classroom=classroom),
        'selected_review_key': selected_review.key if selected_review else '',
        'selected_review': selected_review,
        'review_key': review_key,
        'classroom': classroom,
        'available_slots': {f'{section}_{module}' for section, module in required_modules},
        'has_english_m1': ('english', 'm1') in required_modules,
        'has_english_m2': ('english', 'm2') in required_modules,
        'has_math_m1': ('math', 'm1') in required_modules,
        'has_math_m2': ('math', 'm2') in required_modules,
    })

def _build_test_start_overview(test_obj, user):
    rows = []
    total_questions = 0
    total_seconds = 0
    for section, module in get_test_sequence(test_obj):
        queryset = _module_questions_queryset(test_obj, section, module)
        question_count = queryset.count() if queryset is not None else 0
        duration_seconds = _module_duration_seconds(user, section)
        total_questions += question_count
        total_seconds += duration_seconds
        rows.append({
            'section': section,
            'section_label': 'Reading and Writing' if section == 'english' else 'Mathematics',
            'module': module,
            'module_number': 1 if module == 'm1' else 2,
            'question_count': question_count,
            'duration_minutes': max(round(duration_seconds / 60), 1),
        })
    return {
        'module_rows': rows,
        'total_questions': total_questions,
        'total_modules': len(rows),
        'total_duration_minutes': max(round(total_seconds / 60), 1) if rows else 0,
    }


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

    resumable_stage = _get_resumable_stage(user, test)
    if resumable_stage:
        return redirect('test', pk=test.name)

    completed_review = TestReview.objects.filter(
        user=user,
        test=test,
        score__isnull=False,
        **_classroom_scope_filter(None),
    ).order_by('-created_at').first()

    if completed_review:
        return redirect(_results_url_for_test(test, review_key=completed_review.key))

    has_active_attempt = False

    return render(
        request,
        'test/test_modules.html',
        {
            'test': test,
            'has_active_attempt': has_active_attempt,
            **_build_test_start_overview(test, user),
        }
    )


def _normalize_review_choice_letter(value):
    raw = str(value or '').strip().upper()
    if not raw:
        return ''
    if raw in {'A', 'B', 'C', 'D'}:
        return raw
    prefixed = re.match(r'^([ABCD])(?:\s|[\.)\-:：])', raw)
    if prefixed:
        return prefixed.group(1)
    any_letter = re.search(r'[ABCD]', raw)
    return any_letter.group(0) if any_letter else ''


def _strip_review_choice_prefix(value, letter):
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    if text.startswith('IMAGE:'):
        return text

    target = str(letter or '').strip().upper()
    if target not in {'A', 'B', 'C', 'D'}:
        return text

    patterns = [
        rf'^{target}\s+{target}\s*[\.\)\-:]?\s*',
        rf'^{target}{target}\s*[\.\)\-:]?\s*',
        rf'^{target}\s*[\.\)\-:]\s*',
        rf'^{target}\s+',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
    return text


def _review_question_payload(question, section):
    """Serialize a review question safely and keep cleaned choices server-side.

    Review pages must not depend on JS to show the question body. If JS fails,
    the template still renders passage, question text and answer choices.
    """
    if not question:
        return {}

    if section == 'math':
        return {
            'id': question.id,
            'passage': question.passage or '',
            'number': question.number or 0,
            'question': question.question or '',
            'a': _strip_review_choice_prefix(question.get_a() or '', 'A'),
            'b': _strip_review_choice_prefix(question.get_b() or '', 'B'),
            'c': _strip_review_choice_prefix(question.get_c() or '', 'C'),
            'd': _strip_review_choice_prefix(question.get_d() or '', 'D'),
            'type': bool(getattr(question, 'written', False)),
            'written': bool(getattr(question, 'written', False)),
            'graph': question.get_graph() or '',
        }

    return {
        'id': question.id,
        'passage': question.passage or '',
        'number': question.number or 0,
        'question': question.question or '',
        'a': _strip_review_choice_prefix(question.a or '', 'A'),
        'b': _strip_review_choice_prefix(question.b or '', 'B'),
        'c': _strip_review_choice_prefix(question.c or '', 'C'),
        'd': _strip_review_choice_prefix(question.d or '', 'D'),
        'graph': question.graph_url() or '',
        'response_type': getattr(question, 'response_type', 'multiple_choice'),
        'written': getattr(question, 'response_type', 'multiple_choice') == 'open_text',
        'reference_answer': reference_answer(question),
    }


def _review_choices_payload(question, section):
    payload = _review_question_payload(question, section)
    choices = []
    for letter in ('A', 'B', 'C', 'D'):
        content = payload.get(letter.lower(), '') or ''
        is_image = isinstance(content, str) and content.startswith('IMAGE:')
        choices.append({
            'letter': letter,
            'content': '' if is_image else content,
            'is_image': is_image,
            'image_url': content[6:] if is_image else '',
        })
    return choices

def _review_prev_answer_next(module_obj, question_model, question_id):
    """Return prev id, user's answer, next id using the real module question order.

    The old code used TestModule.find_answer(), which depends on the raw order of
    submitted answers. If that payload order is stale or shuffled, Review navigation
    jumps from Q1 to the last question and Next can become disabled. This function
    sorts by the actual question numbers while still reading the user's answer from
    the submitted payload.
    """
    previous, current_answer, future = '', '', ''
    target_id = str(question_id)

    try:
        payload = json.loads(module_obj.answers or '{"answers": []}')
        answer_items = payload.get('answers', []) or []
    except Exception:
        answer_items = []

    answer_lookup = {}
    raw_ids = []
    for item in answer_items:
        item_id = item.get('questionID') or item.get('question_id') or item.get('id')
        if item_id is None:
            continue
        item_id = str(item_id)
        if item_id not in raw_ids:
            raw_ids.append(item_id)
        raw_answer = item.get('answer')
        answer_lookup[item_id] = '' if raw_answer is None else str(raw_answer)

    current_answer = answer_lookup.get(target_id, '')

    ordered_ids = []
    if raw_ids:
        questions = question_model.objects.filter(id__in=raw_ids).only('id', 'number')
        number_map = {str(q.id): (q.number if q.number is not None else 10_000, q.id) for q in questions}
        ordered_ids = sorted(
            [qid for qid in raw_ids if qid in number_map],
            key=lambda qid: (number_map[qid][0], raw_ids.index(qid)),
        )

    if target_id not in ordered_ids:
        module_map = {'m1': 'module_1', 'm2': 'module_2', 'module_1': 'module_1', 'module_2': 'module_2'}
        module_name = module_map.get(getattr(module_obj, 'module', ''), getattr(module_obj, 'module', ''))
        qs = question_model.objects.all()
        if getattr(module_obj, 'test_id', None):
            qs = qs.filter(test=module_obj.test)
        if module_name:
            qs = qs.filter(module=module_name)
        ordered_ids = [str(q.id) for q in qs.order_by('number', 'id').only('id', 'number')]

    if target_id in ordered_ids:
        idx = ordered_ids.index(target_id)
        previous = ordered_ids[idx - 1] if idx > 0 else ''
        future = ordered_ids[idx + 1] if idx < len(ordered_ids) - 1 else ''

    return previous, current_answer, future


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
        attempt_id=review.attempt_id,
        classroom_id=review.classroom_id,
    ).first()

    if not module_obj:
        if request.user == review.user and review.test:
            return redirect('test', pk=review.test.name)
        return HttpResponse('Review for this section is unavailable because a retake is currently in progress.')
    if not _module_contains_question(module_obj, id):
        raise Http404('This question is not part of the selected attempt module.')

    review_question_model = English_Question if section == 'english' else Math_Question if section == 'math' else None
    if review_question_model:
        prev, answer, new = _review_prev_answer_next(module_obj, review_question_model, id)
    else:
        prev, answer, new = module_obj.find_answer(question_id=id)
    prev = f'/sat/question/{key}/{section}/{module}/{prev}' if prev else ''
    new = f'/sat/question/{key}/{section}/{module}/{new}' if new else ''

    attempts = list(TestReview.objects.filter(
        user=review.user,
        test=review.test,
        score__isnull=False,
        classroom_id=review.classroom_id,
    ).order_by('-created_at'))
    results_url = _review_results_url(review, classroom=review.classroom)
    attempt_options = _build_review_attempt_options(
        attempts,
        review,
        section=section,
        module=module,
        question_id=id,
        classroom=review.classroom,
    )

    if section == 'english':
        question = English_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_eng.html', {
            'question': question,
            'question_payload': _review_question_payload(question, section),
            'review_choices': _review_choices_payload(question, section),
            'answered_choice': '' if question.is_open_text else _normalize_review_choice_letter(answer),
            'correct_choice': '' if question.is_open_text else _normalize_review_choice_letter(question.answer),
            'answered': answer,
            'answer_is_correct': check_english_answer(question, answer),
            'prev': prev,
            'next': new,
            'test': review.test,
            'review': review,
            'results_url': results_url,
            'attempts': attempts,
            'attempt_options': attempt_options,
            'selected_review_key': review.key,
        })

    if section == 'math':
        question = Math_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_math.html', {
            'question': question,
            'question_payload': _review_question_payload(question, section),
            'review_choices': _review_choices_payload(question, section),
            'answered_choice': _normalize_review_choice_letter(answer),
            'correct_choice': _normalize_review_choice_letter(question.answer),
            'answered': answer,
            'answer_is_correct': check_written(answer, question.answer),
            'prev': prev,
            'next': new,
            'test': review.test,
            'review': review,
            'results_url': results_url,
            'attempts': attempts,
            'attempt_options': attempt_options,
            'selected_review_key': review.key,
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
        test_stage.save(update_fields=['stage', 'updated_at'])

    if test_stage.stage > len(sequence):
        return redirect('sat_menu')

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
            return redirect('sat_menu')
        test_stage.stage += 1
        test_stage.save(update_fields=['stage', 'updated_at'])
        return redirect('makeup_test_module', pk=makeup_test.name)

    module_name = f'module_{module[1]}'

    if section == 'english':
        questions = makeup_test.get_module_questions(section, module_name)
        if questions.exists():
            runtime = _makeup_module_runtime(test_stage, section, module, questions)
            if runtime['redirect_url']:
                return redirect(runtime['redirect_url'])
            context = {
                'questions': questions,
                'module': module,
                'test': makeup_test,
                'section': section,
                'is_makeup': True,
            }
            context.update(runtime['context'])
            return render(request, 'test/makeup_eng.html', context)

    if section == 'math':
        questions = makeup_test.get_module_questions(section, module_name)
        if questions.exists():
            runtime = _makeup_module_runtime(test_stage, section, module, questions)
            if runtime['redirect_url']:
                return redirect(runtime['redirect_url'])
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
            context = {
                'questions': questions,
                'questions_data': questions_data,
                'module': module,
                'test': makeup_test,
                'section': section,
                'is_makeup': True,
            }
            context.update(runtime['context'])
            return render(request, 'test/test_math.html', context)

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
    test_stage, created = _get_or_create_regular_test_stage(user, test, stage=1)

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
        attempt_id=test_stage.attempt_id,
        **_classroom_scope_filter(None),
    )

    if existing_module.exists():

        finished = advance_test_stage(test_stage)

        if finished:
            return redirect('results', test=test)

        return module_test(request, pk=test.name)

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

            return module_test(request, pk=test.name)

        runtime = _regular_module_runtime(test_stage, section, module, questions, classroom=None)
        if runtime['redirect_url']:
            return redirect(runtime['redirect_url'])
        context = {
            'questions': questions,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds,
        }
        context.update(runtime['context'])
        return render(request, 'test/test_eng.html', context)

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

            return module_test(request, pk=test.name)

        runtime = _regular_module_runtime(test_stage, section, module, questions, classroom=None)
        if runtime['redirect_url']:
            return redirect(runtime['redirect_url'])

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

        context = {
            'questions': questions,
            'questions_data': questions_data,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds,
        }
        context.update(runtime['context'])
        return render(request, 'test/test_math.html', context)

    return HttpResponse("You dont have permission")

def rankings(request, pk):
    results = TestReview.objects.filter(test__name=pk).order_by('-score', 'user')[:50]
    return render(request, 'test/features/rankings.html', {'results': results})


@allowed_users(['Admin'])
def results_by_user(request, test, username):
    test_obj = Test.objects.get(name=test)
    user = User.objects.get(username=username)
    classroom = None

    review_key = request.GET.get('review_key')
    attempts = list(TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at'))
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

    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review, classroom=classroom)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id, classroom=classroom)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    status.update(_section_submission_status(required_modules, missing_modules))

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
                    is_correct = bool(q_obj and check_english_answer(q_obj, answer.get('answer')))
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
        'attempt_options': _build_review_attempt_options(attempts, selected_review, classroom=classroom),
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
                    is_correct = bool(db_question and check_english_answer(db_question, answer.get('answer')))
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
                return redirect('sat_menu')  # Return to the canonical classroom entry page
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

    classroom = _get_classroom_context_from_id(user, request.POST.get('classroom_id'), test_obj=test)

    if classroom is None and not user_has_test_access(user, test):
        return HttpResponse(
            f"Test '{pk}' is not assigned to your account.",
            status=403
        )

    stage, _ = _get_or_create_regular_test_stage(user, test, stage=1, classroom=classroom)

    # Try to restart the section
    response = stage.resolve_section(section)

    if response:
        if classroom:
            return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)
        return redirect('test', pk=test.name)
    else:
        # Retake limit exceeded
        user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'
        
        return render(request, 'sat/retake_limit_exceeded.html', {
            'test_name': pk,
            'section': section,
            'retakes_used': stage.retake_count,
            'max_retakes': stage.get_max_retakes(),
            'user_group': user_group,
            'classroom': classroom,
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

    units = list(
        VocabularyUnit.objects.filter(is_active=True)
        .prefetch_related('words')
        .order_by('order', 'id')
    )
    summary = get_vocabulary_summary(request.user)
    unit_rows = build_unit_progress_rows(request.user, units=units)
    recent_attempts = VocabularyQuizAttempt.objects.filter(
        user=request.user,
        classroom__isnull=True,
    )[:5]

    return render(request, 'sat/vocabulary.html', {
        'units': units,
        'summary': summary,
        'unit_rows': unit_rows,
        'recent_attempts': recent_attempts,
    })


def _get_vocabulary_flashcards_context(request, classroom=None):
    """Build a tracked, one-card-at-a-time vocabulary study deck."""
    units = list(
        VocabularyUnit.objects.filter(is_active=True)
        .prefetch_related('words')
        .order_by('order', 'id')
    )

    selected_unit = None
    selected_unit_id = request.GET.get('unit')
    if selected_unit_id and selected_unit_id.isdigit():
        selected_unit = next((unit for unit in units if unit.id == int(selected_unit_id)), None)
    if selected_unit is None:
        selected_unit = next(
            (unit for unit in units if any(word.is_active for word in unit.words.all())),
            None,
        )

    tracking_classroom = _resolve_vocabulary_tracking_classroom(request, classroom)
    progress_rows = build_unit_progress_rows(
        request.user,
        classroom=tracking_classroom,
        units=units,
        include_words=True,
    )
    progress_by_unit = {row['unit'].id: row for row in progress_rows}
    selected_row = progress_by_unit.get(selected_unit.id) if selected_unit else None
    flashcard_words = selected_row['words'] if selected_row else []

    if classroom:
        mark_url = reverse('classroom_vocabulary_flashcard_mark', args=[classroom.id])
    else:
        mark_url = reverse('vocabulary_flashcard_mark')

    return {
        'units': units,
        'unit_rows': progress_rows,
        'selected_unit': selected_unit,
        'selected_unit_progress': selected_row,
        'flashcard_words': flashcard_words,
        'summary': get_vocabulary_summary(request.user, classroom=tracking_classroom),
        'mark_url': mark_url,
        'classroom': classroom,
    }


def _resolve_vocabulary_tracking_classroom(request, classroom):
    if not classroom:
        return None
    membership = ClassroomMembership.objects.filter(
        classroom=classroom,
        user=request.user,
        role='student',
        status='approved',
    ).first()
    return classroom if membership else None


def _mark_vocabulary_flashcard(request, classroom=None):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required.'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = request.POST

    word_id = payload.get('word_id')
    outcome = str(payload.get('outcome') or '').strip().lower()
    if outcome not in {'again', 'learning', 'known'}:
        return JsonResponse({'ok': False, 'error': 'Invalid review outcome.'}, status=400)

    word = get_object_or_404(
        VocabularyWord.objects.select_related('unit'),
        id=word_id,
        is_active=True,
        unit__is_active=True,
    )
    tracking_classroom = _resolve_vocabulary_tracking_classroom(request, classroom)
    progress = record_word_review(
        user=request.user,
        word=word,
        classroom=tracking_classroom,
        outcome=outcome,
    )
    if tracking_classroom:
        sync_vocabulary_review_progress(tracking_classroom, request.user, progress)

    return JsonResponse({
        'ok': True,
        'tracked': True,
        'word_id': word.id,
        'status': progress.status,
        'times_seen': progress.times_seen,
        'accuracy_percent': progress.accuracy_percent,
    })


@login_required(login_url='/login/')
@require_POST
def vocabulary_flashcard_mark(request):
    return _mark_vocabulary_flashcard(request)


@login_required(login_url='/login/')
@require_POST
def classroom_vocabulary_flashcard_mark(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)
    if redirect_response:
        return JsonResponse({'ok': False, 'error': 'Classroom access denied.'}, status=403)
    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('vocabulary'):
            return JsonResponse({'ok': False, 'error': 'Vocabulary access is disabled.'}, status=403)
    return _mark_vocabulary_flashcard(request, classroom=classroom)


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
@ensure_csrf_cookie
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
            'units': units,
            'unit_rows': build_unit_progress_rows(request.user, units=units, include_words=True),
            'summary': get_vocabulary_summary(request.user),
        })

    if slug == 'flashcards':
        return render(request, 'sat/vocabulary_flashcards.html', _get_vocabulary_flashcards_context(request))

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
        'units': units,
        'unit_rows': build_unit_progress_rows(request.user, units=units),
        'summary': get_vocabulary_summary(request.user),
        'recent_attempts': VocabularyQuizAttempt.objects.filter(user=request.user, classroom__isnull=True)[:5],
    })

def _vocabulary_quiz_redirect(classroom=None):
    if classroom:
        return redirect('classroom_vocabulary_section', classroom_id=classroom.id, slug='practice-quiz')
    return redirect('vocabulary_practice_quiz')


def _generate_vocabulary_quiz_questions(selected_units, requested_count, mode):
    selected_words = [
        word
        for unit in selected_units
        for word in unit.words.all()
        if word.is_active
    ]
    random.shuffle(selected_words)

    meaning_pool = list(dict.fromkeys(word.meaning for word in selected_words))
    word_pool = list(dict.fromkeys(word.word for word in selected_words))
    questions = []

    def build_for_direction(word_obj, direction):
        if direction == VocabularyQuizAttempt.MODE_MEANING_TO_WORD:
            answer = word_obj.word
            pool = [value for value in word_pool if value != answer]
            prompt = f'Which word matches this meaning? “{word_obj.meaning}”'
        else:
            answer = word_obj.meaning
            pool = [value for value in meaning_pool if value != answer]
            prompt = f"What is the meaning of '{word_obj.word}'?"

        random.shuffle(pool)
        wrong_answers = pool[:3]
        if len(wrong_answers) < 3:
            return None
        choices = [answer, *wrong_answers]
        random.shuffle(choices)
        return {
            'word_id': word_obj.id,
            'unit_id': word_obj.unit_id,
            'unit': word_obj.unit.title,
            'question': prompt,
            'choices': choices,
            'answer': answer,
            'word': word_obj.word,
            'mode': direction,
        }

    for word_obj in selected_words:
        if len(questions) >= requested_count:
            break
        direction = mode
        if mode == VocabularyQuizAttempt.MODE_MIXED:
            direction = random.choice([
                VocabularyQuizAttempt.MODE_WORD_TO_MEANING,
                VocabularyQuizAttempt.MODE_MEANING_TO_WORD,
            ])
        question = build_for_direction(word_obj, direction)
        if question is None:
            alternate = (
                VocabularyQuizAttempt.MODE_MEANING_TO_WORD
                if direction == VocabularyQuizAttempt.MODE_WORD_TO_MEANING
                else VocabularyQuizAttempt.MODE_WORD_TO_MEANING
            )
            question = build_for_direction(word_obj, alternate)
        if question:
            questions.append(question)
    return questions, len(selected_words)


def _start_vocabulary_quiz(request, classroom=None):
    if request.method != 'POST':
        return _vocabulary_quiz_redirect(classroom)

    selected_ids = [int(value) for value in request.POST.getlist('units') if value.isdigit()]
    mode = request.POST.get('quiz_mode') or VocabularyQuizAttempt.MODE_MIXED
    valid_modes = {choice[0] for choice in VocabularyQuizAttempt.MODE_CHOICES}
    if mode not in valid_modes:
        mode = VocabularyQuizAttempt.MODE_MIXED

    if not selected_ids:
        messages.error(request, 'Select at least one unit.')
        return _vocabulary_quiz_redirect(classroom)

    try:
        requested_count = int(request.POST.get('question_count') or 0)
    except (TypeError, ValueError):
        requested_count = 0
    if requested_count < 1:
        messages.error(request, 'Question count must be at least 1.')
        return _vocabulary_quiz_redirect(classroom)

    selected_units = list(
        VocabularyUnit.objects.filter(id__in=selected_ids, is_active=True)
        .prefetch_related('words')
        .order_by('order', 'id')
    )
    available_words = sum(
        1 for unit in selected_units for word in unit.words.all() if word.is_active
    )
    if available_words < 4:
        messages.error(request, 'You need at least 4 active words in the selected units.')
        return _vocabulary_quiz_redirect(classroom)
    if requested_count > available_words:
        messages.error(request, f'Only {available_words} active words are available in the selected units.')
        return _vocabulary_quiz_redirect(classroom)

    questions, _ = _generate_vocabulary_quiz_questions(selected_units, requested_count, mode)
    if not questions:
        messages.error(request, 'Could not generate quiz questions. Add more distinct words and meanings.')
        return _vocabulary_quiz_redirect(classroom)
    if len(questions) < requested_count:
        messages.info(request, f'Generated {len(questions)} valid questions from the available unique choices.')

    request.session['vocab_quiz_questions'] = questions
    request.session['vocab_quiz_units'] = [unit.title for unit in selected_units]
    request.session['vocab_quiz_mode'] = mode
    request.session['vocab_quiz_started_at'] = timezone.now().isoformat()
    request.session['vocab_quiz_classroom_id'] = classroom.id if classroom else None

    return render(request, 'sat/vocabulary_practice_quiz_test.html', {
        'questions': questions,
        'selected_units': selected_units,
        'requested_count': len(questions),
        'quiz_mode': mode,
        'classroom': classroom,
    })


def _finish_vocabulary_quiz(request, classroom=None):
    if request.method != 'POST':
        return _vocabulary_quiz_redirect(classroom)

    questions = request.session.get('vocab_quiz_questions') or []
    if not questions:
        messages.error(request, 'This quiz session expired. Start a new quiz.')
        return _vocabulary_quiz_redirect(classroom)

    selected_units = request.session.get('vocab_quiz_units') or []
    quiz_mode = request.session.get('vocab_quiz_mode') or VocabularyQuizAttempt.MODE_MIXED
    started_at_raw = request.session.get('vocab_quiz_started_at')
    started_at = parse_datetime(started_at_raw) if started_at_raw else None
    if started_at and timezone.is_naive(started_at):
        started_at = timezone.make_aware(started_at)
    started_at = started_at or timezone.now()
    duration_seconds = max(int((timezone.now() - started_at).total_seconds()), 0)

    score = 0
    results = []
    tracking_classroom = _resolve_vocabulary_tracking_classroom(request, classroom)

    with transaction.atomic():
        attempt = VocabularyQuizAttempt.objects.create(
            user=request.user,
            classroom=tracking_classroom,
            mode=quiz_mode,
            selected_units=selected_units,
            total_questions=len(questions),
            started_at=started_at,
            duration_seconds=duration_seconds,
        )

        answer_rows = []
        for index, question in enumerate(questions):
            user_answer = request.POST.get(f'question_{index}', '')
            is_correct = user_answer == question['answer']
            if is_correct:
                score += 1

            word = VocabularyWord.objects.filter(id=question.get('word_id')).first()
            if word:
                record_word_review(
                    user=request.user,
                    word=word,
                    classroom=tracking_classroom,
                    outcome='correct' if is_correct else 'incorrect',
                )

            answer_rows.append(VocabularyQuizAnswer(
                attempt=attempt,
                word=word,
                prompt=question['question'],
                selected_answer=user_answer,
                correct_answer=question['answer'],
                is_correct=is_correct,
            ))
            results.append({
                'question': question['question'],
                'user_answer': user_answer,
                'correct_answer': question['answer'],
                'is_correct': is_correct,
                'unit': question['unit'],
                'word': question['word'],
                'mode': question.get('mode', quiz_mode),
            })

        VocabularyQuizAnswer.objects.bulk_create(answer_rows)
        percentage = round((score / len(questions)) * 100, 2) if questions else 0
        attempt.score = score
        attempt.percentage = percentage
        attempt.save(update_fields=['score', 'percentage'])

    if tracking_classroom:
        sync_vocabulary_student_progress(tracking_classroom, request.user)
    summary = get_vocabulary_summary(request.user, classroom=tracking_classroom)

    for key in (
        'vocab_quiz_questions',
        'vocab_quiz_units',
        'vocab_quiz_mode',
        'vocab_quiz_started_at',
        'vocab_quiz_classroom_id',
    ):
        request.session.pop(key, None)

    return render(request, 'sat/vocabulary_practice_quiz_result.html', {
        'results': results,
        'score': score,
        'total': len(questions),
        'total_questions': len(questions),
        'percentage': percentage,
        'selected_units': selected_units,
        'attempt': attempt,
        'summary': summary,
        'classroom': classroom,
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
    return _start_vocabulary_quiz(request)


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
    return _finish_vocabulary_quiz(request)


@login_required(login_url='/login/')
def vocabulary_flashcards(request):
    return render(request, 'sat/vocabulary_flashcards.html', _get_vocabulary_flashcards_context(request))



SUPPORT_LESSON_LOOKAHEAD_DAYS = 28
SUPPORT_LESSON_LIST_LOOKAHEAD_DAYS = 14
SUPPORT_NOTE_MAX_LENGTH = 1200


def is_manager(user):
    return bool(
        user.is_authenticated
        and user.groups.filter(name__iexact='Manager').exists()
    )


def _support_teacher_admin_allowed(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name__iexact='Admin').exists()
    )


def _support_feedback_view_allowed(user):
    """Private ratings/comments are visible only to staff-side teaching roles."""
    if not user.is_authenticated:
        return False
    return bool(
        _support_teacher_admin_allowed(user)
        or is_manager(user)
        or is_teacher(user)
        or hasattr(user, 'support_teacher_profile')
    )


def _user_can_access_support_classes(user):
    """Return whether a user belongs to the support-class ecosystem."""
    if not user.is_authenticated:
        return False
    if _support_teacher_admin_allowed(user) or is_manager(user) or is_teacher(user):
        return True
    if hasattr(user, 'support_teacher_profile'):
        return True
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved',
        classroom__is_active=True,
    ).exists()


def _user_can_book_support_lessons(user):
    """Only approved classroom students may create support requests."""
    if not user.is_authenticated:
        return False
    if _support_teacher_admin_allowed(user) or is_manager(user) or is_teacher(user):
        return False
    if hasattr(user, 'support_teacher_profile'):
        return False
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved',
        classroom__is_active=True,
    ).exists()


def _support_class_access_guard(request):
    if _user_can_access_support_classes(request.user):
        return None
    return classroom_access_denied(
        request,
        message=(
            'Book Support Classes becomes available after you join an active '
            'classroom and your teacher approves the request.'
        ),
        status_code=403,
    )


def _support_booking_student_guard(request):
    if _user_can_book_support_lessons(request.user):
        return None
    messages.error(request, 'Only approved classroom students can request support lessons.')
    return classroom_access_denied(
        request,
        message='Only approved classroom students can request support lessons.',
        status_code=403,
    )


def _normalize_time_for_compare(value):
    if not value:
        return value
    return value.replace(second=0, microsecond=0)


def _make_local_datetime(day, time_value):
    current_tz = timezone.get_current_timezone()
    naive_value = datetime.combine(day, time_value)
    if timezone.is_naive(naive_value):
        return timezone.make_aware(naive_value, current_tz)
    return naive_value


def _support_booking_overlap_q(start_at, end_at):
    return Q(start_at__lt=end_at, end_at__gt=start_at)


def _sync_support_booking_completion_queryset(queryset=None):
    return 0


def _sync_support_booking_completion(booking):
    booking.mark_completed_if_past()
    return booking


def _availability_slot_datetimes(day, availability):
    """Yield concrete slots from one recurring weekly availability window."""
    window_start = _make_local_datetime(day, availability.start_time)
    window_end = _make_local_datetime(day, availability.end_time)
    total_minutes = max(0, int((window_end - window_start).total_seconds() // 60))
    if total_minutes <= 0:
        return

    requested_duration = max(15, int(availability.slot_duration_minutes or total_minutes))
    duration_minutes = min(requested_duration, total_minutes)
    buffer_minutes = max(0, int(availability.buffer_minutes or 0))
    cursor = window_start
    duration_delta = timedelta(minutes=duration_minutes)
    step_delta = timedelta(minutes=duration_minutes + buffer_minutes)

    while cursor + duration_delta <= window_end:
        yield cursor, cursor + duration_delta
        cursor += step_delta


def _build_support_teacher_slots(
    teacher,
    days=SUPPORT_LESSON_LOOKAHEAD_DAYS,
    include_unavailable=False,
    respect_notice=True,
):
    """Build teacher-plannable slots from recurring weekly windows.

    Sessions, rather than individual student bookings, own the teacher's time.
    Legacy scheduled bookings without a session are still considered so old
    data cannot overlap a newly planned group session.
    """
    now_value = timezone.now()
    start_date = timezone.localdate()
    end_date = start_date + timedelta(days=days)
    notice_hours = teacher.min_booking_notice_hours or 0 if respect_notice else 0
    notice_cutoff = now_value + timedelta(hours=notice_hours)

    availability_by_day = defaultdict(list)
    for item in teacher.availabilities.filter(is_active=True).order_by('day_of_week', 'start_time'):
        availability_by_day[item.day_of_week].append(item)

    range_start = _make_local_datetime(start_date, datetime.min.time())
    range_end = _make_local_datetime(end_date + timedelta(days=1), datetime.min.time())

    booked_ranges = list(
        SupportLessonSession.objects.filter(
            teacher=teacher,
            status=SupportLessonSession.STATUS_SCHEDULED,
            start_at__lt=range_end,
            end_at__gt=range_start,
        ).values_list('start_at', 'end_at')
    )
    booked_ranges += list(
        SupportLessonBooking.objects.filter(
            teacher=teacher,
            session__isnull=True,
            status=SupportLessonBooking.STATUS_SCHEDULED,
            start_at__lt=range_end,
            end_at__gt=range_start,
        ).values_list('start_at', 'end_at')
    )

    slots = []
    for offset in range(days + 1):
        day = start_date + timedelta(days=offset)
        for availability in availability_by_day.get(day.weekday(), []):
            for start_at, end_at in _availability_slot_datetimes(day, availability):
                is_past = end_at <= now_value
                is_too_soon = start_at < notice_cutoff
                is_booked = any(
                    booked_start < end_at and booked_end > start_at
                    for booked_start, booked_end in booked_ranges
                )
                is_available = not is_past and not is_too_soon and not is_booked

                if not include_unavailable and not is_available:
                    continue

                local_start = timezone.localtime(start_at)
                local_end = timezone.localtime(end_at)
                if is_booked:
                    state = 'booked'
                elif is_past:
                    state = 'past'
                elif is_too_soon:
                    state = 'too_soon'
                else:
                    state = 'available'

                slots.append({
                    'availability': availability,
                    'start_at': start_at,
                    'end_at': end_at,
                    'is_booked': is_booked,
                    'is_too_soon': is_too_soon,
                    'is_past': is_past,
                    'is_available': is_available,
                    'state': state,
                    'value': f'{start_at.isoformat()}|{end_at.isoformat()}',
                    'date_key': local_start.date().isoformat(),
                    'date_label': local_start.strftime('%d %b %Y'),
                    'day_label': local_start.strftime('%A'),
                    'short_day_label': local_start.strftime('%a'),
                    'time_label': f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}",
                    'duration_minutes': max(0, int((end_at - start_at).total_seconds() // 60)),
                    'note': availability.note,
                })

    return sorted(slots, key=lambda item: item['start_at'])


def _group_support_slots(slots):
    grouped = []
    by_date = defaultdict(list)
    for slot in slots:
        by_date[slot['date_key']].append(slot)
    for date_key, rows in by_date.items():
        grouped.append({
            'date_key': date_key,
            'date_label': rows[0]['date_label'],
            'day_label': rows[0]['day_label'],
            'short_day_label': rows[0]['short_day_label'],
            'slots': rows,
            'available_count': sum(1 for row in rows if row['is_available']),
        })
    return grouped


def _parse_support_lesson_slot(slot_value):
    try:
        start_raw, end_raw = (slot_value or '').split('|', 1)
    except ValueError:
        return None, None

    start_at = parse_datetime(start_raw)
    end_at = parse_datetime(end_raw)
    current_tz = timezone.get_current_timezone()
    if start_at and timezone.is_naive(start_at):
        start_at = timezone.make_aware(start_at, current_tz)
    if end_at and timezone.is_naive(end_at):
        end_at = timezone.make_aware(end_at, current_tz)
    return start_at, end_at


def _find_support_teacher_slot(teacher, start_at, end_at, include_unavailable=True, respect_notice=False):
    if not start_at or not end_at or end_at <= start_at:
        return None
    local_start = timezone.localtime(start_at)
    day_offset = (local_start.date() - timezone.localdate()).days
    if day_offset < 0 or day_offset > SUPPORT_LESSON_LOOKAHEAD_DAYS:
        return None
    slots = _build_support_teacher_slots(
        teacher,
        days=max(day_offset, 0),
        include_unavailable=include_unavailable,
        respect_notice=respect_notice,
    )
    for slot in slots:
        if slot['start_at'] == start_at and slot['end_at'] == end_at:
            return slot
    return None


def _support_subject_tokens(subjects):
    return [
        value.strip()
        for value in re.split(r'[,/|]+', subjects or '')
        if value.strip()
    ]


def _validated_support_url(value):
    value = (value or '').strip()
    if not value:
        return ''
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return value[:500]


def _support_safe_next_url(request, fallback='support_teacher_planner'):
    next_url = request.POST.get('next', '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback)


def _active_support_titles():
    topic_qs = SupportLessonTopic.objects.filter(is_active=True).order_by('sort_order', 'name')
    return (
        SupportLessonTitle.objects.filter(is_active=True, topics__is_active=True)
        .prefetch_related(Prefetch('topics', queryset=topic_qs, to_attr='active_topics'))
        .distinct()
        .order_by('sort_order', 'name')
    )


def _student_support_conflict(student, start_at, end_at, exclude_booking_id=None):
    if not start_at or not end_at:
        return False
    qs = SupportLessonBooking.objects.filter(
        student=student,
        status=SupportLessonBooking.STATUS_SCHEDULED,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)
    return qs.exists()


def _find_open_support_topic_session(teacher, lesson_topic, student):
    sessions = (
        SupportLessonSession.objects.filter(
            teacher=teacher,
            lesson_topic=lesson_topic,
            status=SupportLessonSession.STATUS_SCHEDULED,
            is_open_for_requests=True,
            start_at__gt=timezone.now(),
        )
        .prefetch_related('bookings')
        .order_by('start_at')
    )
    for session in sessions:
        active_count = sum(
            1 for booking in session.bookings.all()
            if booking.status != SupportLessonBooking.STATUS_CANCELLED
        )
        if active_count >= session.max_students:
            continue
        if _student_support_conflict(student, session.start_at, session.end_at):
            continue
        return session
    return None


def _assign_booking_to_support_session(booking, session):
    booking.session = session
    booking.teacher = session.teacher
    booking.lesson_topic = session.lesson_topic or booking.lesson_topic
    booking.lesson_title = booking.lesson_topic.title if booking.lesson_topic_id else booking.lesson_title
    booking.start_at = session.start_at
    booking.end_at = session.end_at
    booking.status = SupportLessonBooking.STATUS_SCHEDULED
    booking.meeting_link = session.meeting_link or session.teacher.meeting_link
    booking.cancelled_by = ''
    booking.cancelled_at = None
    booking.cancellation_reason = ''
    booking.save()
    return booking


@login_required(login_url='/login/')
def support_teacher_list(request):
    denied = _support_class_access_guard(request)
    if denied:
        return denied

    query = request.GET.get('q', '').strip()
    selected_subject = request.GET.get('subject', '').strip()
    can_view_feedback = _support_feedback_view_allowed(request.user)

    teachers = (
        SupportTeacherProfile.objects.filter(is_active=True)
        .select_related('user')
        .annotate(
            display_completed_lessons=(
                Count(
                    'sessions',
                    filter=Q(sessions__status=SupportLessonSession.STATUS_COMPLETED),
                    distinct=True,
                )
                + Count(
                    'bookings',
                    filter=Q(
                        bookings__status=SupportLessonBooking.STATUS_COMPLETED,
                        bookings__session__isnull=True,
                    ),
                    distinct=True,
                )
            ),
        )
    )
    if can_view_feedback:
        teachers = teachers.annotate(
            display_avg_rating=Avg(
                'reviews__rating',
                filter=Q(reviews__booking__status=SupportLessonBooking.STATUS_COMPLETED),
            ),
            display_reviews_count=Count(
                'reviews',
                filter=Q(reviews__booking__status=SupportLessonBooking.STATUS_COMPLETED),
                distinct=True,
            ),
        )
    if query:
        teachers = teachers.filter(
            Q(display_name__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(subjects__icontains=query)
            | Q(bio__icontains=query)
        )
    if selected_subject:
        teachers = teachers.filter(subjects__icontains=selected_subject)

    teacher_cards = []
    subject_choices = set()
    for teacher in teachers:
        for token in _support_subject_tokens(teacher.subjects):
            subject_choices.add(token)
        if can_view_feedback:
            teacher.display_rating = round(float(teacher.display_avg_rating), 1) if teacher.display_avg_rating else None
        teacher_cards.append({
            'teacher': teacher,
            'subjects': _support_subject_tokens(teacher.subjects),
        })

    my_upcoming_bookings = []
    next_booking = None
    if _user_can_book_support_lessons(request.user):
        my_upcoming_bookings = list(
            SupportLessonBooking.objects.filter(
                student=request.user,
                status=SupportLessonBooking.STATUS_SCHEDULED,
                end_at__gte=timezone.now(),
            ).select_related('teacher', 'teacher__user', 'lesson_title', 'lesson_topic').order_by('start_at')[:5]
        )
        next_booking = my_upcoming_bookings[0] if my_upcoming_bookings else None

    return render(request, 'sat/support_teacher_list.html', {
        'teacher_cards': teacher_cards,
        'my_upcoming_bookings': my_upcoming_bookings,
        'next_booking': next_booking,
        'query': query,
        'selected_subject': selected_subject,
        'subject_choices': sorted(subject_choices, key=str.lower),
        'can_book': _user_can_book_support_lessons(request.user),
        'can_view_private_feedback': can_view_feedback,
        'timezone_name': str(timezone.get_current_timezone()),
    })


@login_required(login_url='/login/')
def support_teacher_detail(request, teacher_id):
    denied = _support_class_access_guard(request)
    if denied:
        return denied

    can_view_feedback = _support_feedback_view_allowed(request.user)
    teacher_qs = SupportTeacherProfile.objects.select_related('user').annotate(
        display_completed_lessons=(
            Count(
                'sessions',
                filter=Q(sessions__status=SupportLessonSession.STATUS_COMPLETED),
                distinct=True,
            )
            + Count(
                'bookings',
                filter=Q(
                    bookings__status=SupportLessonBooking.STATUS_COMPLETED,
                    bookings__session__isnull=True,
                ),
                distinct=True,
            )
        ),
    )
    if can_view_feedback:
        teacher_qs = teacher_qs.annotate(
            display_avg_rating=Avg(
                'reviews__rating',
                filter=Q(reviews__booking__status=SupportLessonBooking.STATUS_COMPLETED),
            ),
            display_reviews_count=Count(
                'reviews',
                filter=Q(reviews__booking__status=SupportLessonBooking.STATUS_COMPLETED),
                distinct=True,
            ),
        )
    teacher = get_object_or_404(teacher_qs, id=teacher_id, is_active=True)

    reviews = []
    rating_distribution = []
    if can_view_feedback:
        private_reviews_qs = teacher.reviews.filter(
            booking__status=SupportLessonBooking.STATUS_COMPLETED,
        ).select_related('student', 'booking', 'booking__lesson_topic').order_by('-created_at')
        reviews = list(private_reviews_qs[:30])
        rating_counts = {value: 0 for value in range(1, 6)}
        for row in private_reviews_qs.values('rating').annotate(total=Count('id')):
            rating_counts[row['rating']] = row['total']
        total_reviews = sum(rating_counts.values())
        rating_distribution = [
            {
                'rating': rating,
                'count': rating_counts[rating],
                'percent': round((rating_counts[rating] / total_reviews) * 100) if total_reviews else 0,
            }
            for rating in range(5, 0, -1)
        ]

    my_bookings = []
    if _user_can_book_support_lessons(request.user):
        my_bookings = list(
            SupportLessonBooking.objects.filter(
                teacher=teacher,
                student=request.user,
            ).select_related('teacher', 'lesson_title', 'lesson_topic', 'session').order_by('-created_at')[:10]
        )

    upcoming_sessions = list(
        SupportLessonSession.objects.filter(
            teacher=teacher,
            status=SupportLessonSession.STATUS_SCHEDULED,
            is_open_for_requests=True,
            start_at__gt=timezone.now(),
        ).select_related('lesson_topic', 'lesson_topic__title').order_by('start_at')[:6]
    )

    return render(request, 'sat/support_teacher_detail.html', {
        'teacher': teacher,
        'subjects': _support_subject_tokens(teacher.subjects),
        'lesson_titles': _active_support_titles(),
        'my_bookings': my_bookings,
        'upcoming_sessions': upcoming_sessions,
        'reviews': reviews,
        'rating_distribution': rating_distribution,
        'can_book': _user_can_book_support_lessons(request.user),
        'can_view_private_feedback': can_view_feedback,
        'timezone_name': str(timezone.get_current_timezone()),
        'is_profile_owner': request.user == teacher.user,
    })


@login_required(login_url='/login/')
def support_teacher_profile_edit(request):
    profile = getattr(request.user, 'support_teacher_profile', None)
    if not profile:
        return HttpResponseForbidden('Only support teachers can edit a support profile.')

    if request.method == 'POST':
        form = SupportTeacherSelfProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your support teacher profile was updated.')
            return redirect('support_teacher_profile_edit')
    else:
        form = SupportTeacherSelfProfileForm(instance=profile)

    return render(request, 'sat/support_teacher_profile_edit.html', {
        'teacher': profile,
        'form': form,
        'subjects': _support_subject_tokens(profile.subjects),
        'timezone_name': str(timezone.get_current_timezone()),
    })


@login_required(login_url='/login/')
@require_POST
def support_teacher_availability_add(request):
    profile = getattr(request.user, 'support_teacher_profile', None)
    if not profile:
        return HttpResponseForbidden('Only support teachers can manage availability.')

    form = SupportTeacherSelfAvailabilityForm(request.POST)
    if form.is_valid():
        availability = form.save(commit=False)
        availability.teacher = profile
        try:
            availability.full_clean()
            availability.save()
            messages.success(request, 'Availability window added.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect('support_teacher_planner')


@login_required(login_url='/login/')
@require_POST
def support_teacher_availability_delete(request, availability_id):
    profile = getattr(request.user, 'support_teacher_profile', None)
    if not profile:
        return HttpResponseForbidden('Only support teachers can manage availability.')
    availability = get_object_or_404(SupportTeacherAvailability, id=availability_id, teacher=profile)
    availability.delete()
    messages.success(request, 'Availability window removed.')
    return redirect('support_teacher_planner')


@login_required(login_url='/login/')
@require_POST
def book_support_lesson(request, teacher_id):
    denied = _support_class_access_guard(request)
    if denied:
        return denied
    booking_denied = _support_booking_student_guard(request)
    if booking_denied:
        return booking_denied

    teacher = get_object_or_404(SupportTeacherProfile, id=teacher_id, is_active=True)
    student_note = request.POST.get('student_note', '').strip()
    try:
        title_id = int(request.POST.get('lesson_title', '0'))
        topic_id = int(request.POST.get('lesson_topic', '0'))
    except (TypeError, ValueError):
        title_id = topic_id = 0

    title = SupportLessonTitle.objects.filter(id=title_id, is_active=True).first()
    topic = SupportLessonTopic.objects.select_related('title').filter(
        id=topic_id,
        title=title,
        is_active=True,
        title__is_active=True,
    ).first()
    if not title or not topic:
        messages.error(request, 'Choose a valid title and topic.')
        return redirect('support_teacher_detail', teacher_id=teacher.id)

    if len(student_note) > SUPPORT_NOTE_MAX_LENGTH:
        messages.error(request, f'Your lesson goal must be {SUPPORT_NOTE_MAX_LENGTH} characters or fewer.')
        return redirect('support_teacher_detail', teacher_id=teacher.id)

    now_value = timezone.now()
    existing = SupportLessonBooking.objects.filter(
        student=request.user,
        teacher=teacher,
        lesson_topic=topic,
    ).filter(
        Q(status=SupportLessonBooking.STATUS_REQUESTED)
        | Q(status=SupportLessonBooking.STATUS_SCHEDULED, end_at__gte=now_value)
    ).first()
    if existing:
        messages.info(request, 'You already have an active request or upcoming lesson for this topic with this teacher.')
        return redirect('my_support_lessons')

    try:
        with transaction.atomic():
            locked_teacher = SupportTeacherProfile.objects.select_for_update().get(pk=teacher.pk)
            User.objects.select_for_update().get(pk=request.user.pk)

            # Re-check under row locks so a double-click / parallel request cannot
            # create two active requests for the same student, teacher and topic.
            existing = SupportLessonBooking.objects.filter(
                student=request.user,
                teacher=locked_teacher,
                lesson_topic=topic,
            ).filter(
                Q(status=SupportLessonBooking.STATUS_REQUESTED)
                | Q(status=SupportLessonBooking.STATUS_SCHEDULED, end_at__gte=timezone.now())
            ).first()
            if existing:
                messages.info(request, 'You already have an active request or upcoming lesson for this topic with this teacher.')
                return redirect('my_support_lessons')

            session = _find_open_support_topic_session(locked_teacher, topic, request.user)
            booking = SupportLessonBooking.objects.create(
                teacher=locked_teacher,
                student=request.user,
                session=session,
                lesson_title=title,
                lesson_topic=topic,
                start_at=session.start_at if session else None,
                end_at=session.end_at if session else None,
                status=(
                    SupportLessonBooking.STATUS_SCHEDULED
                    if session else SupportLessonBooking.STATUS_REQUESTED
                ),
                student_note=student_note,
                meeting_link=(session.meeting_link if session else '') or locked_teacher.meeting_link,
            )
    except IntegrityError:
        # The database constraints are the final guard for concurrent submissions.
        messages.info(request, 'That support request already exists. Your current booking was kept unchanged.')
        return redirect('my_support_lessons')

    if booking.status == SupportLessonBooking.STATUS_SCHEDULED:
        local_start = timezone.localtime(booking.start_at)
        messages.success(
            request,
            f'You joined the existing {topic.name} group on {local_start:%d %b at %H:%M}.',
        )
    else:
        messages.success(
            request,
            f'Request sent for {title.name} → {topic.name}. {teacher.name} will plan the time and students with the same topic will be grouped together.',
        )
    return redirect('my_support_lessons')


@login_required(login_url='/login/')
def my_support_lessons(request):
    denied = _support_class_access_guard(request)
    if denied:
        return denied
    if not _user_can_book_support_lessons(request.user):
        if hasattr(request.user, 'support_teacher_profile'):
            return redirect('support_teacher_planner')
        if is_manager(request.user):
            return redirect('manager_dashboard')

    bookings = list(
        SupportLessonBooking.objects.filter(student=request.user)
        .select_related('teacher', 'teacher__user', 'lesson_title', 'lesson_topic', 'session')
        .order_by('-created_at')
    )
    now_value = timezone.now()
    waiting_requests = [b for b in bookings if b.status == SupportLessonBooking.STATUS_REQUESTED]
    upcoming_bookings = sorted(
        [
            b for b in bookings
            if b.status == SupportLessonBooking.STATUS_SCHEDULED
            and b.end_at
            and b.end_at >= now_value
        ],
        key=lambda b: b.start_at,
    )
    history_bookings = [
        b for b in bookings
        if b.status not in {SupportLessonBooking.STATUS_REQUESTED, SupportLessonBooking.STATUS_SCHEDULED}
        or (b.status == SupportLessonBooking.STATUS_SCHEDULED and b.end_at and b.end_at < now_value)
    ]

    return render(request, 'sat/my_support_lessons.html', {
        'waiting_requests': waiting_requests,
        'upcoming_bookings': upcoming_bookings,
        'history_bookings': history_bookings,
        'next_booking': upcoming_bookings[0] if upcoming_bookings else None,
        'completed_count': sum(1 for b in history_bookings if b.status == SupportLessonBooking.STATUS_COMPLETED),
        'timezone_name': str(timezone.get_current_timezone()),
    })


@login_required(login_url='/login/')
@require_POST
def cancel_support_lesson(request, booking_id):
    denied = _support_class_access_guard(request)
    if denied:
        return denied

    booking = get_object_or_404(
        SupportLessonBooking.objects.select_related('teacher'),
        id=booking_id,
        student=request.user,
        status__in=[SupportLessonBooking.STATUS_REQUESTED, SupportLessonBooking.STATUS_SCHEDULED],
    )
    if not booking.student_can_cancel:
        notice = booking.teacher.cancellation_notice_hours
        messages.error(
            request,
            f'Online cancellation closes {notice} hour{"s" if notice != 1 else ""} before the lesson. Contact the teacher if you need help.',
        )
        return redirect('my_support_lessons')

    booking.status = SupportLessonBooking.STATUS_CANCELLED
    booking.cancellation_reason = request.POST.get('reason', '').strip()[:500]
    booking.cancelled_by = SupportLessonBooking.CANCELLED_BY_STUDENT
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=['status', 'cancellation_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])
    messages.success(request, 'Support request cancelled.' if not booking.start_at else 'Support lesson cancelled.')
    return redirect('my_support_lessons')


@login_required(login_url='/login/')
@require_POST
def leave_support_lesson_feedback(request, booking_id):
    denied = _support_class_access_guard(request)
    if denied:
        return denied

    booking = get_object_or_404(
        SupportLessonBooking.objects.select_related('teacher', 'teacher__user'),
        id=booking_id,
        student=request.user,
    )
    if not booking.can_receive_feedback:
        messages.error(request, 'Feedback is available once after a completed lesson.')
        return redirect('my_support_lessons')

    try:
        rating = int(request.POST.get('rating', '0'))
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        messages.error(request, 'Rating must be between 1 and 5.')
        return redirect('my_support_lessons')

    feedback = request.POST.get('feedback', '').strip()
    if len(feedback) > 1200:
        messages.error(request, 'Your review comment must be 1,200 characters or fewer.')
        return redirect('my_support_lessons')
    try:
        SupportTeacherReview.objects.create(
            booking=booking,
            teacher=booking.teacher,
            student=request.user,
            rating=rating,
            feedback=feedback,
        )
    except IntegrityError:
        messages.info(request, 'Feedback for this lesson has already been submitted.')
        return redirect('my_support_lessons')

    messages.success(request, 'Thank you. Your private feedback was saved for teachers and managers.')
    return redirect('my_support_lessons')


def _support_booking_manager_profile(user, booking):
    if _support_teacher_admin_allowed(user):
        return booking.teacher
    profile = getattr(user, 'support_teacher_profile', None)
    if profile and profile.pk == booking.teacher_id:
        return profile
    return None


@login_required(login_url='/login/')
@require_POST
def manage_support_lesson(request, booking_id):
    """Manage an individual student booking (including no-show inside a group)."""
    booking = get_object_or_404(
        SupportLessonBooking.objects.select_related('teacher', 'student', 'teacher__user', 'session'),
        id=booking_id,
    )
    profile = _support_booking_manager_profile(request.user, booking)
    if not profile:
        return HttpResponseForbidden('You cannot manage this support lesson.')

    action = request.POST.get('action', '').strip()
    now_value = timezone.now()
    if action == 'no_show':
        if booking.status != SupportLessonBooking.STATUS_SCHEDULED:
            messages.error(request, 'Only scheduled lessons can be marked as no-show.')
        elif booking.start_at and now_value < booking.start_at and not _support_teacher_admin_allowed(request.user):
            messages.error(request, 'A future lesson cannot be marked as no-show.')
        else:
            booking.status = SupportLessonBooking.STATUS_NO_SHOW
            booking.marked_completed_at = now_value
            booking.save(update_fields=['status', 'marked_completed_at', 'updated_at'])
            messages.success(request, f'{booking.student.username} marked as no-show.')
    elif action == 'cancel':
        if booking.status not in {SupportLessonBooking.STATUS_REQUESTED, SupportLessonBooking.STATUS_SCHEDULED}:
            messages.error(request, 'Only active requests can be cancelled.')
        else:
            booking.status = SupportLessonBooking.STATUS_CANCELLED
            booking.cancellation_reason = request.POST.get('cancellation_reason', '').strip()[:500]
            booking.cancelled_by = (
                SupportLessonBooking.CANCELLED_BY_ADMIN
                if _support_teacher_admin_allowed(request.user)
                else SupportLessonBooking.CANCELLED_BY_TEACHER
            )
            booking.cancelled_at = now_value
            booking.save(update_fields=['status', 'cancellation_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])
            messages.success(request, 'Student request cancelled.')
    elif action == 'complete' and not booking.session_id:
        if booking.status != SupportLessonBooking.STATUS_SCHEDULED:
            messages.error(request, 'Only scheduled lessons can be completed.')
        else:
            booking.status = SupportLessonBooking.STATUS_COMPLETED
            booking.marked_completed_at = now_value
            booking.save(update_fields=['status', 'marked_completed_at', 'updated_at'])
            messages.success(request, 'Lesson marked as completed.')
    else:
        messages.error(request, 'Use the group-session controls for this action.')
    return redirect(_support_safe_next_url(request))


@login_required(login_url='/login/')
@require_POST
def schedule_support_topic_session(request):
    profile = getattr(request.user, 'support_teacher_profile', None)
    is_admin = _support_teacher_admin_allowed(request.user)
    if not profile and not is_admin:
        return HttpResponseForbidden('Only support teachers can schedule topic sessions.')

    if is_admin and request.POST.get('teacher_id'):
        profile = get_object_or_404(SupportTeacherProfile, id=request.POST.get('teacher_id'))
    if not profile:
        return HttpResponseForbidden('No support teacher profile selected.')

    try:
        topic_id = int(request.POST.get('lesson_topic', '0'))
        max_students = int(request.POST.get('max_students', '20'))
    except (TypeError, ValueError):
        topic_id = 0
        max_students = 20
    topic = get_object_or_404(SupportLessonTopic.objects.select_related('title'), id=topic_id, is_active=True)
    max_students = max(1, min(max_students, 100))
    start_at, end_at = _parse_support_lesson_slot(request.POST.get('slot', ''))
    slot = _find_support_teacher_slot(profile, start_at, end_at, include_unavailable=True, respect_notice=False)
    if not slot or not slot['is_available']:
        messages.error(request, 'That time is not available anymore. Choose another teacher slot.')
        return redirect('support_teacher_planner')

    meeting_link = _validated_support_url(request.POST.get('meeting_link', ''))
    if meeting_link is None:
        messages.error(request, 'Enter a valid http:// or https:// meeting link.')
        return redirect('support_teacher_planner')

    with transaction.atomic():
        locked_profile = SupportTeacherProfile.objects.select_for_update().get(pk=profile.pk)
        locked_slot = _find_support_teacher_slot(
            locked_profile,
            start_at,
            end_at,
            include_unavailable=True,
            respect_notice=False,
        )
        if not locked_slot or not locked_slot['is_available']:
            messages.error(request, 'That time was just taken by another session.')
            return redirect('support_teacher_planner')

        session = SupportLessonSession.objects.create(
            teacher=locked_profile,
            lesson_topic=topic,
            start_at=start_at,
            end_at=end_at,
            meeting_link=meeting_link or locked_profile.meeting_link,
            teacher_note=request.POST.get('teacher_note', '').strip()[:1200],
            max_students=max_students,
            is_open_for_requests=request.POST.get('is_open_for_requests') in {'1', 'true', 'on', 'yes'},
            created_by=request.user,
        )

        pending = list(
            SupportLessonBooking.objects.select_for_update()
            .filter(
                teacher=locked_profile,
                lesson_topic=topic,
                status=SupportLessonBooking.STATUS_REQUESTED,
            )
            .select_related('student')
            .order_by('created_at')
        )
        assigned = 0
        skipped_conflicts = 0
        for booking in pending:
            if assigned >= max_students:
                break
            if _student_support_conflict(booking.student, start_at, end_at, exclude_booking_id=booking.id):
                skipped_conflicts += 1
                continue
            _assign_booking_to_support_session(booking, session)
            assigned += 1

    message = f'{topic.name} scheduled for {timezone.localtime(start_at):%d %b, %H:%M}. {assigned} student request(s) grouped into the session.'
    if skipped_conflicts:
        message += f' {skipped_conflicts} request(s) stayed pending because of time conflicts.'
    messages.success(request, message)
    return redirect('support_teacher_planner')


@login_required(login_url='/login/')
@require_POST
def manage_support_session(request, session_id):
    session = get_object_or_404(
        SupportLessonSession.objects.select_related('teacher', 'lesson_topic'),
        id=session_id,
    )
    profile = getattr(request.user, 'support_teacher_profile', None)
    if not _support_teacher_admin_allowed(request.user) and (not profile or profile.pk != session.teacher_id):
        return HttpResponseForbidden('You cannot manage this support session.')

    action = request.POST.get('action', '').strip()
    now_value = timezone.now()
    if action == 'update':
        link = _validated_support_url(request.POST.get('meeting_link', ''))
        if link is None:
            messages.error(request, 'Enter a valid meeting link.')
            return redirect('support_teacher_planner')
        session.meeting_link = link
        session.teacher_note = request.POST.get('teacher_note', '').strip()[:1200]
        session.is_open_for_requests = request.POST.get('is_open_for_requests') in {'1', 'true', 'on', 'yes'}
        session.save(update_fields=['meeting_link', 'teacher_note', 'is_open_for_requests', 'updated_at'])
        if link:
            session.bookings.filter(status=SupportLessonBooking.STATUS_SCHEDULED).update(meeting_link=link)
        messages.success(request, 'Group session updated.')
    elif action == 'complete':
        if session.status != SupportLessonSession.STATUS_SCHEDULED:
            messages.error(request, 'Only scheduled sessions can be completed.')
        elif now_value < session.start_at and not _support_teacher_admin_allowed(request.user):
            messages.error(request, 'The session cannot be completed before it starts.')
        else:
            session.status = SupportLessonSession.STATUS_COMPLETED
            session.is_open_for_requests = False
            session.save(update_fields=['status', 'is_open_for_requests', 'updated_at'])
            session.bookings.filter(status=SupportLessonBooking.STATUS_SCHEDULED).update(
                status=SupportLessonBooking.STATUS_COMPLETED,
                marked_completed_at=now_value,
                updated_at=now_value,
            )
            messages.success(request, 'Group session and attending bookings marked completed.')
    elif action == 'cancel':
        if session.status != SupportLessonSession.STATUS_SCHEDULED:
            messages.error(request, 'Only scheduled sessions can be cancelled.')
        else:
            session.status = SupportLessonSession.STATUS_CANCELLED
            session.is_open_for_requests = False
            session.save(update_fields=['status', 'is_open_for_requests', 'updated_at'])
            cancelled_by = (
                SupportLessonBooking.CANCELLED_BY_ADMIN
                if _support_teacher_admin_allowed(request.user)
                else SupportLessonBooking.CANCELLED_BY_TEACHER
            )
            reason = request.POST.get('cancellation_reason', '').strip()[:500]
            session.bookings.filter(status=SupportLessonBooking.STATUS_SCHEDULED).update(
                status=SupportLessonBooking.STATUS_CANCELLED,
                cancelled_by=cancelled_by,
                cancelled_at=now_value,
                cancellation_reason=reason,
                updated_at=now_value,
            )
            messages.success(request, 'Group session cancelled.')
    elif action == 'open':
        if session.status != SupportLessonSession.STATUS_SCHEDULED or session.end_at <= now_value:
            messages.error(request, 'Only an upcoming scheduled session can accept new matching requests.')
        elif session.available_seats <= 0:
            messages.error(request, 'This session is already full.')
        else:
            session.is_open_for_requests = True
            session.save(update_fields=['is_open_for_requests', 'updated_at'])
            messages.success(request, 'New matching requests can now join this session automatically.')
    elif action == 'close':
        session.is_open_for_requests = False
        session.save(update_fields=['is_open_for_requests', 'updated_at'])
        messages.success(request, 'Automatic enrollment for this session is closed.')
    else:
        messages.error(request, 'Unknown session action.')
    return redirect('support_teacher_planner')


@login_required(login_url='/login/')
def support_teacher_planner(request):
    profile = getattr(request.user, 'support_teacher_profile', None)
    is_admin = _support_teacher_admin_allowed(request.user)
    if not profile and not is_admin:
        return HttpResponseForbidden('Only support teachers can view this planner.')

    teacher_id = request.GET.get('teacher')
    if is_admin and teacher_id:
        profile = get_object_or_404(SupportTeacherProfile, id=teacher_id)
    if not profile:
        profile = SupportTeacherProfile.objects.select_related('user').first()
        if not profile:
            return HttpResponseForbidden('No support teacher profile exists yet.')

    now_value = timezone.now()
    pending_requests = list(
        SupportLessonBooking.objects.filter(
            teacher=profile,
            status=SupportLessonBooking.STATUS_REQUESTED,
        ).select_related('student', 'lesson_title', 'lesson_topic').order_by('lesson_topic__name', 'created_at')
    )
    pending_by_topic = {}
    for booking in pending_requests:
        key = booking.lesson_topic_id or f'legacy-{booking.topic}'
        row = pending_by_topic.setdefault(key, {
            'lesson_topic': booking.lesson_topic,
            'title': booking.display_title,
            'topic': booking.display_topic,
            'bookings': [],
        })
        row['bookings'].append(booking)
    pending_groups = list(pending_by_topic.values())
    for row in pending_groups:
        row['count'] = len(row['bookings'])
        row['oldest_created_at'] = min(booking.created_at for booking in row['bookings'])
    # Demand first, then oldest request. This gives the teacher a sensible
    # recommendation for the next class without removing teacher control.
    pending_groups.sort(key=lambda row: (-row['count'], row['oldest_created_at']))

    upcoming_sessions = list(
        SupportLessonSession.objects.filter(
            teacher=profile,
            status=SupportLessonSession.STATUS_SCHEDULED,
            end_at__gte=now_value - timedelta(hours=3),
        )
        .select_related('lesson_topic', 'lesson_topic__title')
        .prefetch_related('bookings__student')
        .order_by('start_at')
    )
    history_sessions = list(
        SupportLessonSession.objects.filter(teacher=profile)
        .exclude(status=SupportLessonSession.STATUS_SCHEDULED)
        .select_related('lesson_topic', 'lesson_topic__title')
        .prefetch_related('bookings__student')
        .order_by('-start_at')[:30]
    )
    legacy_bookings = list(
        SupportLessonBooking.objects.filter(
            teacher=profile,
            session__isnull=True,
            status=SupportLessonBooking.STATUS_SCHEDULED,
            start_at__isnull=False,
        ).select_related('student').order_by('start_at')[:30]
    )
    available_slots = _build_support_teacher_slots(
        profile,
        days=14,
        include_unavailable=False,
        respect_notice=False,
    )
    recommended_group = next(
        (row for row in pending_groups if row.get('lesson_topic') is not None),
        None,
    )
    recommended_slot = available_slots[0] if available_slots else None
    reviews = profile.reviews.select_related(
        'student', 'booking', 'booking__lesson_topic'
    ).order_by('-created_at')[:30]

    return render(request, 'sat/support_teacher_planner.html', {
        'teacher': profile,
        'pending_groups': pending_groups,
        'pending_request_count': len(pending_requests),
        'upcoming_sessions': upcoming_sessions,
        'history_sessions': history_sessions,
        'legacy_bookings': legacy_bookings,
        'slot_groups': _group_support_slots(available_slots),
        'recommended_group': recommended_group,
        'recommended_slot': recommended_slot,
        'lesson_titles': _active_support_titles(),
        'reviews': reviews,
        'today_session_count': sum(1 for s in upcoming_sessions if timezone.localdate(s.start_at) == timezone.localdate()),
        'completed_count': SupportLessonBooking.objects.filter(
            teacher=profile,
            status=SupportLessonBooking.STATUS_COMPLETED,
        ).count(),
        'average_rating': profile.average_rating,
        'is_admin': is_admin,
        'is_own_profile': request.user == profile.user,
        'availabilities': profile.availabilities.order_by('day_of_week', 'start_time'),
        'availability_form': SupportTeacherSelfAvailabilityForm(initial={'is_active': True}) if request.user == profile.user else None,
        'teacher_choices': SupportTeacherProfile.objects.select_related('user').order_by('sort_order', 'display_name') if is_admin else [],
        'timezone_name': str(timezone.get_current_timezone()),
    })


@login_required(login_url='/login/')
def manager_dashboard(request):
    if not (_support_teacher_admin_allowed(request.user) or is_manager(request.user)):
        return HttpResponseForbidden('Manager access required.')

    now_value = timezone.now()
    classroom_teachers = (
        User.objects.filter(owned_classrooms__is_active=True)
        .annotate(
            active_classrooms_count=Count(
                'owned_classrooms',
                filter=Q(owned_classrooms__is_active=True),
                distinct=True,
            ),
            approved_students_count=Count(
                'owned_classrooms__memberships__user',
                filter=Q(
                    owned_classrooms__is_active=True,
                    owned_classrooms__memberships__role='student',
                    owned_classrooms__memberships__status='approved',
                ),
                distinct=True,
            ),
            pending_students_count=Count(
                'owned_classrooms__memberships__user',
                filter=Q(
                    owned_classrooms__is_active=True,
                    owned_classrooms__memberships__role='student',
                    owned_classrooms__memberships__status='pending',
                ),
                distinct=True,
            ),
        )
        .order_by('-approved_students_count', 'first_name', 'username')
    )

    support_teachers = (
        SupportTeacherProfile.objects.select_related('user')
        .annotate(
            assigned_students_count=Count(
                'bookings__student',
                filter=~Q(bookings__status=SupportLessonBooking.STATUS_CANCELLED),
                distinct=True,
            ),
            waiting_requests_count=Count(
                'bookings',
                filter=Q(bookings__status=SupportLessonBooking.STATUS_REQUESTED),
                distinct=True,
            ),
            upcoming_students_count=Count(
                'bookings__student',
                filter=Q(
                    bookings__status=SupportLessonBooking.STATUS_SCHEDULED,
                    bookings__end_at__gte=now_value,
                ),
                distinct=True,
            ),
            completed_session_count=Count(
                'sessions',
                filter=Q(sessions__status=SupportLessonSession.STATUS_COMPLETED),
                distinct=True,
            ),
            legacy_completed_booking_count=Count(
                'bookings',
                filter=Q(
                    bookings__status=SupportLessonBooking.STATUS_COMPLETED,
                    bookings__session__isnull=True,
                ),
                distinct=True,
            ),
            manager_avg_rating=Avg(
                'reviews__rating',
                filter=Q(reviews__booking__status=SupportLessonBooking.STATUS_COMPLETED),
            ),
            manager_reviews_count=Count(
                'reviews',
                filter=Q(reviews__booking__status=SupportLessonBooking.STATUS_COMPLETED),
                distinct=True,
            ),
        )
        .order_by('sort_order', 'display_name', 'user__username')
    )
    for teacher in support_teachers:
        teacher.manager_rating = round(float(teacher.manager_avg_rating), 1) if teacher.manager_avg_rating is not None else None
        teacher.manager_completed_classes = (
            int(teacher.completed_session_count or 0)
            + int(teacher.legacy_completed_booking_count or 0)
        )

    recent_reviews = list(
        SupportTeacherReview.objects.select_related(
            'teacher', 'teacher__user', 'student', 'booking', 'booking__lesson_topic'
        ).filter(booking__status=SupportLessonBooking.STATUS_COMPLETED).order_by('-created_at')[:40]
    )
    upcoming_sessions = list(
        SupportLessonSession.objects.filter(
            status=SupportLessonSession.STATUS_SCHEDULED,
            end_at__gte=now_value,
        ).select_related('teacher', 'lesson_topic', 'lesson_topic__title').annotate(
            display_student_count=Count(
                'bookings',
                filter=~Q(bookings__status=SupportLessonBooking.STATUS_CANCELLED),
            )
        ).order_by('start_at')[:30]
    )

    total_students = ClassroomMembership.objects.filter(
        role='student', status='approved', classroom__is_active=True
    ).values('user_id').distinct().count()
    total_support_students = SupportLessonBooking.objects.exclude(
        status=SupportLessonBooking.STATUS_CANCELLED
    ).values('student_id').distinct().count()

    return render(request, 'sat/manager_dashboard.html', {
        'classroom_teachers': classroom_teachers,
        'support_teachers': support_teachers,
        'recent_reviews': recent_reviews,
        'upcoming_sessions': upcoming_sessions,
        'total_classroom_teachers': classroom_teachers.count(),
        'total_students': total_students,
        'total_support_teachers': support_teachers.count(),
        'total_support_students': total_support_students,
        'waiting_requests_total': SupportLessonBooking.objects.filter(status=SupportLessonBooking.STATUS_REQUESTED).count(),
        'timezone_name': str(timezone.get_current_timezone()),
    })


@login_required(login_url='/login/')
def manager_teacher_detail(request, teacher_id):
    if not (_support_teacher_admin_allowed(request.user) or is_manager(request.user)):
        return HttpResponseForbidden('Manager access required.')

    teacher = get_object_or_404(User, pk=teacher_id)
    classrooms = list(
        Classroom.objects.filter(teacher=teacher)
        .annotate(
            approved_students_count=Count(
                'memberships__user',
                filter=Q(memberships__role='student', memberships__status='approved'),
                distinct=True,
            ),
            pending_students_count=Count(
                'memberships__user',
                filter=Q(memberships__role='student', memberships__status='pending'),
                distinct=True,
            ),
        )
        .order_by('-is_active', '-created_at')
    )

    memberships = list(
        ClassroomMembership.objects.filter(
            classroom__teacher=teacher,
            role='student',
            status='approved',
        )
        .select_related('user', 'classroom')
        .order_by('classroom__name', 'user__first_name', 'user__username')
    )
    students_by_classroom = defaultdict(list)
    unique_student_ids = set()
    for membership in memberships:
        students_by_classroom[membership.classroom_id].append(membership)
        unique_student_ids.add(membership.user_id)

    for classroom in classrooms:
        classroom.manager_students = students_by_classroom.get(classroom.id, [])

    return render(request, 'sat/manager_teacher_detail.html', {
        'teacher': teacher,
        'classrooms': classrooms,
        'total_classrooms': len(classrooms),
        'active_classrooms': sum(1 for classroom in classrooms if classroom.is_active),
        'unique_students_count': len(unique_student_ids),
        'pending_joins_count': sum(int(classroom.pending_students_count or 0) for classroom in classrooms),
    })


@login_required(login_url='/login/')
def manager_classroom_detail(request, classroom_id):
    if not (_support_teacher_admin_allowed(request.user) or is_manager(request.user)):
        return HttpResponseForbidden('Manager access required.')

    classroom = get_object_or_404(Classroom.objects.select_related('teacher'), pk=classroom_id)
    approved_students = list(
        ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student',
            status='approved',
        )
        .select_related('user')
        .order_by('user__first_name', 'user__last_name', 'user__username')
    )
    pending_students = list(
        ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student',
            status='pending',
        )
        .select_related('user')
        .order_by('requested_at')
    )

    return render(request, 'sat/manager_classroom_detail.html', {
        'classroom': classroom,
        'teacher': classroom.teacher,
        'approved_students': approved_students,
        'pending_students': pending_students,
        'approved_students_count': len(approved_students),
        'pending_students_count': len(pending_students),
    })


def is_teacher(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.is_staff or user.groups.filter(name__iexact='teacher').exists():
        return True
    # Classroom ownership is also authoritative for legacy teacher accounts that
    # predate the Teacher group assignment. This keeps teacher-only support
    # feedback and classroom routes available without granting Django staff access.
    return Classroom.objects.filter(teacher=user, is_active=True).exists()


def generate_6_digit_code():
    return f"{random.randint(0, 999999):06d}"


def generate_unique_classroom_code():
    while True:
        code = generate_6_digit_code()
        if not ClassroomJoinCode.objects.filter(code=code).exists():
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
        classroom_type = request.POST.get('classroom_type', Classroom.CLASSROOM_TYPE_SAT).strip().lower()

        if classroom_type not in {Classroom.CLASSROOM_TYPE_SAT, Classroom.CLASSROOM_TYPE_AP}:
            messages.error(request, "Choose a valid classroom type.")
            return redirect('create_classroom')

        if not name:
            messages.error(request, "Classroom name is required.")
            return redirect('create_classroom')

        classroom = Classroom.objects.create(
            teacher=request.user,
            name=name,
            description=description,
            classroom_type=classroom_type,
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

    return render(request, 'sat/create_classroom.html', {
        'classroom_type_choices': Classroom.CLASSROOM_TYPE_CHOICES,
    })

@login_required(login_url='/login/')
def teacher_classroom_dashboard(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    students = ClassroomMembership.objects.filter(
        classroom=classroom,
        role='student'
    ).exclude(status__in=['left', 'removed']).select_related('user').order_by('-requested_at')

    join_code = getattr(classroom, 'join_code', None)

    return render(request, 'sat/teacher_classroom_dashboard.html', {
        'classroom': classroom,
        'students': students,
        'join_code': join_code,
    })

@login_required(login_url='/login/')
@require_POST
def generate_classroom_join_code(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    old_code = ClassroomJoinCode.objects.filter(classroom=classroom).first()
    if old_code:
        old_code.is_active = False
        old_code.save(update_fields=['is_active'])

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

def get_user_approved_student_memberships(user):
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='approved',
        classroom__is_active=True,
    ).select_related('classroom').prefetch_related('section_access')


def get_user_approved_student_membership(user):
    # Backward-compatible helper for older call sites. New classroom UX should
    # use get_user_approved_student_memberships() and show all classrooms.
    return get_user_approved_student_memberships(user).first()


def get_user_pending_student_memberships(user):
    return ClassroomMembership.objects.filter(
        user=user,
        role='student',
        status='pending'
    ).select_related('classroom')


def get_user_pending_student_membership(user):
    # Backward-compatible helper for older call sites.
    return get_user_pending_student_memberships(user).first()


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

def _student_goal_form_context(user, *, form=None, next_url=None):
    goal, _ = StudentGoalProfile.objects.select_related('dream_university').get_or_create(user=user)
    form = form or StudentGoalProfileForm(instance=goal)
    university_filter = Q(is_active=True)
    if goal.dream_university_id:
        university_filter |= Q(pk=goal.dream_university_id)
    universities = [
        {
            'value': f'{StudentGoalProfileForm.UNIVERSITY_PREFIX}{university.pk}',
            'id': university.pk,
            'name': university.name,
            'country': university.country,
            'city': university.city,
            'average_sat_score': university.average_sat_score,
            'qs_rank': university.qs_rank,
            'ranking_source': university.ranking_source,
            'ranking_year': university.ranking_year,
            'score_note': university.score_note,
            'website': university.website,
        }
        for university in DreamUniversity.objects.filter(university_filter)
        .distinct()
        .order_by('sort_order', 'name')
    ]
    return {
        'goal': goal,
        'goal_form': form,
        'goal_universities': universities,
        'goal_form_next': next_url or reverse('sat_menu'),
    }


def _student_global_goal_context(user):
    goal, _ = StudentGoalProfile.objects.select_related('dream_university').get_or_create(user=user)
    scored_reviews = TestReview.objects.filter(
        user=user,
        score__gte=400,
        score__lte=1600,
    )
    latest_review = scored_reviews.order_by('-created_at').first()
    best_score = scored_reviews.aggregate(best=Max('score')).get('best')
    current_score = latest_review.score if latest_review else None
    target_score = goal.target_sat_score or goal.average_sat_score or 1400
    score_gap = max(0, target_score - current_score) if current_score is not None else None

    if current_score is None or target_score <= 400:
        goal_progress_percent = 0
    else:
        goal_progress_percent = round(
            max(0, min(100, ((current_score - 400) / (target_score - 400)) * 100))
        )

    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)
    recent_tests = scored_reviews.filter(created_at__gte=seven_days_ago).count()
    recent_vocab_reviews = VocabularyWordProgress.objects.filter(
        user=user,
        last_reviewed_at__gte=seven_days_ago,
    ).count()
    weekly_momentum = recent_tests + recent_vocab_reviews

    destination = goal.university_name or 'your dream university'
    motivation_messages = [
        f'One focused session today moves you closer to {destination}.',
        'Consistency wins: protect your study block before the day gets busy.',
        'Reviewing one mistake deeply is worth more than rushing through ten questions.',
        f'Your target is {target_score}. Build it one accurate answer at a time.',
        'Small daily progress becomes a major score increase when repeated every week.',
        'Start with the hardest task while your attention is fresh.',
    ]
    if goal.days_remaining is not None:
        motivation_messages.insert(1, f'{goal.days_remaining} days remain. Today is part of the result.')
    if score_gap is not None and score_gap > 0:
        motivation_messages.insert(2, f'Your next mission: close the {score_gap}-point gap with targeted practice.')
    elif score_gap == 0:
        motivation_messages.insert(2, 'You reached your target range. Now protect consistency and accuracy.')

    if goal.days_remaining is None:
        pace_label = 'Set exam date'
        pace_tone = 'setup'
    elif goal.days_remaining <= 14:
        pace_label = 'Final sprint'
        pace_tone = 'urgent'
    elif goal.days_remaining <= 45:
        pace_label = 'Focused phase'
        pace_tone = 'focused'
    else:
        pace_label = 'Steady build'
        pace_tone = 'steady'

    return {
        'goal': goal,
        'goal_is_configured': goal.is_configured,
        'latest_review': latest_review,
        'current_score': current_score,
        'best_score': best_score,
        'target_score': target_score,
        'score_gap': score_gap,
        'goal_progress_percent': goal_progress_percent,
        'weekly_momentum': weekly_momentum,
        'motivation_messages': motivation_messages,
        'pace_label': pace_label,
        'pace_tone': pace_tone,
    }


@login_required(login_url='/login/')
@ensure_csrf_cookie
def classroom_entry(request):
    if is_manager(request.user):
        return redirect('manager_dashboard')

    if is_teacher(request.user):
        return redirect('teacher_classroom_list')

    # Support teachers use their planner as the operational home page.
    # This keeps /sat/ as the single authenticated entry point after the
    # legacy /sat/dashboard/ route was removed.
    if hasattr(request.user, 'support_teacher_profile'):
        return redirect('support_teacher_planner')

    approved_memberships = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='approved',
        classroom__is_active=True,
    ).select_related('classroom').prefetch_related('section_access').order_by('-approved_at', '-requested_at')

    pending_memberships = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='pending'
    ).select_related('classroom').order_by('-requested_at')

    rejected_memberships = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='rejected'
    ).select_related('classroom').order_by('-requested_at')

    context = {
        'approved_memberships': approved_memberships,
        'pending_memberships': pending_memberships,
        'rejected_memberships': rejected_memberships,
        # Backward compatibility for any old template includes.
        'pending_membership': pending_memberships.first(),
        'rejected_membership': rejected_memberships.first(),
    }
    context.update(_student_global_goal_context(request.user))
    context.update(_student_goal_form_context(
        request.user,
        next_url=request.get_full_path(),
    ))
    # Never hard-lock the dashboard behind this modal. Students can open it
    # explicitly, and ?goal=1 is used by edit/setup buttons.
    context['open_goal_modal'] = request.GET.get('goal') == '1'
    return render(request, 'sat/classroom_join.html', context)

@login_required(login_url='/login/')
def submit_classroom_join_request(request):
    if request.method != 'POST':
        return redirect('sat_menu')

    if is_teacher(request.user):
        return HttpResponseForbidden("Teachers cannot submit classroom join requests.")

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
            messages.info(request, "Your request is already pending for this classroom.")
        elif membership.status in ['rejected', 'left', 'removed']:
            membership.status = 'pending'
            membership.requested_at = timezone.now()
            membership.approved_at = None
            membership.left_at = None
            membership.removed_at = None
            membership.save(update_fields=[
                'status',
                'requested_at',
                'approved_at',
                'left_at',
                'removed_at',
            ])
            messages.success(request, "Your join request has been submitted again.")
        return redirect('sat_menu')

    messages.success(request, f'Join request sent to classroom "{join_code.classroom.name}".')
    return redirect('sat_menu')

@login_required(login_url='/login/')
def classroom_join_status(request):
    approved_memberships = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='approved',
        classroom__is_active=True,
    ).select_related('classroom').prefetch_related('section_access').order_by('-approved_at', '-requested_at')

    pending_memberships = get_user_pending_student_memberships(request.user).order_by('-requested_at')

    rejected_memberships = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
        status='rejected'
    ).select_related('classroom').order_by('-requested_at')

    return render(request, 'sat/classroom_join_status.html', {
        'approved_memberships': approved_memberships,
        'pending_memberships': pending_memberships,
        'rejected_memberships': rejected_memberships,
        # Backward compatibility for old template variables.
        'pending_membership': pending_memberships.first(),
        'rejected_membership': rejected_memberships.first(),
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
        ).exclude(status__in=['left', 'removed']).select_related('user').order_by('-requested_at'),
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
        role='student',
        status='pending'
    )

    membership.status = 'approved'
    membership.approved_at = timezone.now()
    membership.left_at = None
    membership.removed_at = None
    membership.save(update_fields=['status', 'approved_at', 'left_at', 'removed_at'])

    for section in ['practice_tests', 'vocabulary', 'admissions']:
        StudentSectionAccess.objects.get_or_create(
            membership=membership,
            section=section,
            defaults={'has_access': False}
        )
    
    recalculate_student_progress_for_classroom(classroom, membership.user)
    
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
        role='student',
        status='pending'
    )

    membership.status = 'rejected'
    membership.approved_at = None
    membership.left_at = None
    membership.removed_at = None
    membership.save(update_fields=['status', 'approved_at', 'left_at', 'removed_at'])

    messages.info(request, f"{membership.user.username}'s request was rejected.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

def classroom_access_denied(
    request,
    classroom=None,
    message="You do not have access to this classroom.",
    status_code=403,
):
    return render(request, 'sat/classroom_access_denied.html', {
        'classroom': classroom,
        'message': message,
    }, status=status_code)

def _student_goal_context(user, classroom, access_map):
    goal, _ = StudentGoalProfile.objects.select_related('dream_university').get_or_create(user=user)

    scored_reviews = TestReview.objects.filter(
        user=user,
        score__gte=400,
        score__lte=1600,
    ).filter(
        Q(classroom=classroom) | Q(classroom__isnull=True)
    )
    latest_review = scored_reviews.order_by('-created_at').first()
    best_score = scored_reviews.aggregate(best=Max('score')).get('best')
    current_score = latest_review.score if latest_review else None

    target_score = goal.target_sat_score or goal.average_sat_score or 1400
    score_gap = max(0, target_score - current_score) if current_score is not None else None
    if current_score is None or target_score <= 400:
        goal_progress_percent = 0
    else:
        goal_progress_percent = round(max(0, min(100, ((current_score - 400) / (target_score - 400)) * 100)))

    progress_records = {
        row.section: row
        for row in StudentProgress.objects.filter(classroom=classroom, student=user)
    }
    practice_progress = progress_records.get('practice_tests')
    vocabulary_progress = progress_records.get('vocabulary')
    admissions_progress = progress_records.get('admissions')

    now = timezone.now()
    next_support_lesson = SupportLessonBooking.objects.filter(
        student=user,
        status=SupportLessonBooking.STATUS_SCHEDULED,
        start_at__gte=now,
    ).select_related('teacher', 'teacher__user').order_by('start_at').first()

    seven_days_ago = now - timedelta(days=7)
    recent_tests = scored_reviews.filter(created_at__gte=seven_days_ago).count()
    recent_vocab_reviews = VocabularyWordProgress.objects.filter(
        user=user,
        classroom=classroom,
        last_reviewed_at__gte=seven_days_ago,
    ).count()
    weekly_momentum = recent_tests + recent_vocab_reviews

    destination = goal.university_name or 'your dream university'
    messages_pool = [
        f"One focused session today moves you closer to {destination}.",
        "Consistency wins: protect your study block before the day gets busy.",
        "Reviewing one mistake deeply is worth more than rushing through ten questions.",
        f"Your target is {target_score}. Build it one accurate answer at a time.",
        "Small daily progress becomes a major score increase when repeated every week.",
        "Start with the hardest task while your attention is fresh.",
    ]
    if goal.days_remaining is not None:
        messages_pool.insert(1, f"{goal.days_remaining} days remain. Today is part of the result.")
    if score_gap is not None and score_gap > 0:
        messages_pool.insert(2, f"Your next mission: close the {score_gap}-point gap with targeted practice.")
    elif score_gap == 0:
        messages_pool.insert(2, "You reached your target range. Now protect consistency and accuracy.")

    focus_cards = []
    if next_support_lesson:
        focus_cards.append({
            'icon': 'bi-person-video3',
            'title': 'Prepare for support class',
            'text': f"Write down three questions before your lesson with {next_support_lesson.teacher.name}.",
            'url': reverse('my_support_lessons'),
            'label': 'Open lesson',
        })
    if access_map.get('practice_tests'):
        focus_cards.append({
            'icon': 'bi-stopwatch',
            'title': 'Complete focused practice',
            'text': 'Finish one timed module, then review every mistake before starting another.',
            'url': reverse('classroom_practice_tests', args=[classroom.id]),
            'label': 'Practice now',
        })
    if access_map.get('vocabulary'):
        focus_cards.append({
            'icon': 'bi-journal-text',
            'title': 'Strengthen vocabulary',
            'text': 'Review a short word set and revisit the terms marked as weak.',
            'url': reverse('classroom_vocabulary', args=[classroom.id]),
            'label': 'Study words',
        })
    if access_map.get('admissions') and len(focus_cards) < 3:
        focus_cards.append({
            'icon': 'bi-mortarboard',
            'title': 'Connect score to admissions',
            'text': 'Review the next admissions task for your dream-university plan.',
            'url': reverse('classroom_admissions', args=[classroom.id]),
            'label': 'Open admissions',
        })

    if goal.days_remaining is None:
        pace_label = 'Set exam date'
        pace_tone = 'setup'
    elif goal.days_remaining <= 14:
        pace_label = 'Final sprint'
        pace_tone = 'urgent'
    elif goal.days_remaining <= 45:
        pace_label = 'Focused phase'
        pace_tone = 'focused'
    else:
        pace_label = 'Steady build'
        pace_tone = 'steady'

    return {
        'goal': goal,
        'goal_is_configured': goal.is_configured,
        'latest_review': latest_review,
        'current_score': current_score,
        'best_score': best_score,
        'target_score': target_score,
        'score_gap': score_gap,
        'goal_progress_percent': goal_progress_percent,
        'practice_progress': practice_progress,
        'vocabulary_progress': vocabulary_progress,
        'admissions_progress': admissions_progress,
        'next_support_lesson': next_support_lesson,
        'weekly_momentum': weekly_momentum,
        'recent_tests': recent_tests,
        'recent_vocab_reviews': recent_vocab_reviews,
        'motivation_messages': messages_pool,
        'focus_cards': focus_cards[:3],
        'pace_label': pace_label,
        'pace_tone': pace_tone,
    }


@login_required(login_url='/login/')
@ensure_csrf_cookie
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
    context = {
        'classroom': classroom,
        'membership': membership,
        'access_map': access_map,
    }
    context.update(_student_goal_context(request.user, classroom, access_map))
    context.update(_student_goal_form_context(
        request.user,
        next_url=request.get_full_path(),
    ))
    # Never hard-lock the dashboard behind this modal. Students can open it
    # explicitly, and ?goal=1 is used by edit/setup buttons.
    context['open_goal_modal'] = request.GET.get('goal') == '1'

    return render(request, 'sat/student_classroom_home.html', context)


def _student_goal_redirect_url(request):
    candidate = (request.POST.get('next') or '').strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse('sat_menu')


@login_required(login_url='/login/')
@require_GET
@ensure_csrf_cookie
def student_goal_csrf(request):
    """Return a fresh CSRF token for the goal modal.

    The dashboard may remain open across login/token rotation or be restored
    from the browser back-forward cache. Refreshing the token immediately
    before the AJAX POST keeps the cookie and submitted token synchronized.
    """
    response = JsonResponse({
        'ok': True,
        'csrfToken': get_token(request),
    })
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    return response


@login_required(login_url='/login/')
def student_goal_settings(request):
    # A user can legitimately have more than one classroom role. For example,
    # a student may own a test classroom while still having an approved student
    # membership elsewhere. The old check rejected every classroom owner before
    # considering the student's memberships, which produced the misleading 403
    # page after pressing "Save my SAT goal".
    has_student_membership = ClassroomMembership.objects.filter(
        user=request.user,
        role='student',
    ).exists()
    has_teacher_only_identity = (
        is_teacher(request.user)
        or Classroom.objects.filter(teacher=request.user).exists()
        or hasattr(request.user, 'support_teacher_profile')
    )
    if has_teacher_only_identity and not has_student_membership:
        return HttpResponseForbidden('Only students can manage SAT goals.')

    if request.method != 'POST':
        return redirect(f"{reverse('sat_menu')}?goal=1")

    goal, _ = StudentGoalProfile.objects.select_related('dream_university').get_or_create(
        user=request.user
    )
    form = StudentGoalProfileForm(request.POST, instance=goal)
    redirect_url = _student_goal_redirect_url(request)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except (ValidationError, IntegrityError) as exc:
            logger.warning('Student goal save validation failed for user %s: %s', request.user.pk, exc)
            if is_ajax:
                return JsonResponse({
                    'ok': False,
                    'errors': {'__all__': ['The goal could not be saved. Please review the selected values.']},
                }, status=400)
            messages.error(request, 'The goal could not be saved. Please review the selected values.')
            return redirect(f"{reverse('sat_menu')}?goal=1")
        except Exception:
            logger.exception('Unexpected student goal save failure for user %s', request.user.pk)
            if is_ajax:
                return JsonResponse({
                    'ok': False,
                    'errors': {'__all__': ['A server error prevented saving. Please try again.']},
                }, status=500)
            messages.error(request, 'A server error prevented saving. Please try again.')
            return redirect(f"{reverse('sat_menu')}?goal=1")

        if is_ajax:
            return JsonResponse({
                'ok': True,
                'redirect_url': redirect_url,
            })
        messages.success(request, 'Your SAT goal has been updated.')
        return redirect(redirect_url)

    if is_ajax:
        return JsonResponse({
            'ok': False,
            'errors': {
                field: [str(message) for message in field_errors]
                for field, field_errors in form.errors.items()
            },
        }, status=400)

    fallback_context = _student_goal_form_context(
        request.user,
        form=form,
        next_url=redirect_url,
    )
    fallback_context.update({
        'form': form,
        'open_goal_modal': True,
    })
    return render(request, 'sat/student_goal_settings.html', fallback_context)


@login_required(login_url='/login/')
def student_goal_settings_legacy(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)
    if redirect_response:
        return redirect_response
    if role != 'student':
        return classroom_access_denied(
            request,
            classroom=classroom,
            message='Only approved students can manage SAT goals.',
        )
    if request.method == 'POST':
        request.POST = request.POST.copy()
        if not request.POST.get('university_choice'):
            legacy_university_id = (request.POST.get('dream_university') or '').strip()
            if legacy_university_id:
                request.POST['university_choice'] = (
                    f'{StudentGoalProfileForm.UNIVERSITY_PREFIX}{legacy_university_id}'
                )
            elif (request.POST.get('custom_university_name') or '').strip():
                request.POST['university_choice'] = StudentGoalProfileForm.OTHER_VALUE
        if not request.POST.get('next'):
            request.POST['next'] = reverse('student_classroom_home', args=[classroom.id])
        return student_goal_settings(request)
    return redirect(f"{reverse('student_classroom_home', args=[classroom.id])}?goal=1")

def get_membership_section_access_map(membership):
    result = {
        'practice_tests': False,
        'vocabulary': False,
        'admissions': False,
    }

    for item in membership.section_access.all():
        result[item.section] = item.has_access

    return result


def get_classroom_manageable_sections(classroom):
    """Return the student resource toggles that make sense for this classroom type.

    SAT classrooms can control SAT practice tests plus shared student resources.
    AP classrooms use AP test assignment separately, but they still need Vocabulary
    and Admissions access toggles. Do not expose SAT practice-tests as an AP toggle.
    """
    shared_sections = [
        {'key': 'vocabulary', 'label': 'Vocabulary'},
        {'key': 'admissions', 'label': 'Admissions'},
    ]

    if classroom.is_ap_classroom:
        return shared_sections

    return [
        {'key': 'practice_tests', 'label': 'SAT Practice Tests'},
        *shared_sections,
    ]

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

    section_options = get_classroom_manageable_sections(classroom)
    section_keys = [section['key'] for section in section_options]

    if request.method == 'POST':
        selected_sections = set(request.POST.getlist('sections'))
        for section in section_keys:
            access_obj, _ = StudentSectionAccess.objects.get_or_create(
                membership=membership,
                section=section,
                defaults={'has_access': False}
            )
            access_obj.has_access = section in selected_sections
            access_obj.save(update_fields=['has_access'])

        messages.success(request, f"Access updated for {membership.user.username}.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    access_map = get_membership_section_access_map(membership)
    section_rows = [
        {
            'key': section['key'],
            'label': section['label'],
            'checked': access_map.get(section['key'], False),
        }
        for section in section_options
    ]

    return render(request, 'sat/update_student_section_access.html', {
        'classroom': classroom,
        'membership': membership,
        'access_map': access_map,
        'section_rows': section_rows,
    })

@login_required(login_url='/login/')
def update_classroom_section_access(request, classroom_id):
    """Save classroom-wide section defaults and apply them to current students.

    This is a persistent classroom policy, so students approved later inherit the
    same section access automatically.
    """
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

    section_options = get_classroom_manageable_sections(classroom)
    section_keys = [section['key'] for section in section_options]

    if request.method == 'POST':
        selected_sections = set(request.POST.getlist('sections'))
        previous_practice_default = ClassroomSectionAccessPolicy.objects.filter(
            classroom=classroom,
            section='practice_tests',
        ).values_list('has_access', flat=True).first()

        for section in section_keys:
            ClassroomSectionAccessPolicy.objects.update_or_create(
                classroom=classroom,
                section=section,
                defaults={'has_access': section in selected_sections},
            )

        for membership in memberships:
            for section in section_keys:
                access_obj, _ = StudentSectionAccess.objects.get_or_create(
                    membership=membership,
                    section=section,
                    defaults={'has_access': False}
                )
                access_obj.has_access = section in selected_sections
                access_obj.save(update_fields=['has_access'])

        # If Practice Tests has just been enabled, materialize any test policy
        # that may already have been configured before students joined.
        if 'practice_tests' in selected_sections and previous_practice_default is not True:
            from .classroom_access_policy import apply_classroom_access_policy_to_membership
            for membership in memberships:
                apply_classroom_access_policy_to_membership(membership)

        messages.success(
            request,
            f"Classroom access policy saved and applied to {len(memberships)} current "
            "student(s). New students will inherit it automatically."
        )
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    section_counts = {s: 0 for s in section_keys}
    for membership in memberships:
        amap = get_membership_section_access_map(membership)
        for section in section_keys:
            if amap.get(section):
                section_counts[section] += 1

    total = len(memberships)
    legacy_majority_access = {
        s: (section_counts[s] > total / 2) for s in section_keys
    } if total else {s: False for s in section_keys}

    saved_policies = {
        item.section: item.has_access
        for item in ClassroomSectionAccessPolicy.objects.filter(
            classroom=classroom,
            section__in=section_keys,
        )
    }
    policy_access = {
        section: saved_policies.get(section, legacy_majority_access[section])
        for section in section_keys
    }

    section_rows = [
        {
            'key': section['key'],
            'label': section['label'],
            'count': section_counts[section['key']],
            'checked': policy_access[section['key']],
        }
        for section in section_options
    ]

    return render(request, 'sat/update_classroom_section_access.html', {
        'classroom': classroom,
        'student_count': total,
        'majority_access': policy_access,
        'section_counts': section_counts,
        'section_rows': section_rows,
        'has_saved_policy': bool(saved_policies),
    })


@login_required(login_url='/login/')
@ensure_csrf_cookie
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
    tracking_classroom = classroom if role == 'student' else None

    if slug == 'word_lists':
        return render(request, 'sat/vocabulary_word_lists.html', {
            'units': units,
            'classroom': classroom,
            'unit_rows': build_unit_progress_rows(request.user, classroom=tracking_classroom, units=units, include_words=True),
            'summary': get_vocabulary_summary(request.user, classroom=tracking_classroom),
        })

    if slug == 'flashcards':
        return render(request, 'sat/vocabulary_flashcards.html', _get_vocabulary_flashcards_context(request, classroom=classroom))

    if slug == 'practice-quiz':
        return render(request, 'sat/vocabulary_practice_quiz.html', {
            'units': units,
            'classroom': classroom,
            'unit_rows': build_unit_progress_rows(request.user, classroom=tracking_classroom, units=units),
            'summary': get_vocabulary_summary(request.user, classroom=tracking_classroom),
            'recent_attempts': VocabularyQuizAttempt.objects.filter(user=request.user, classroom=tracking_classroom)[:5],
        })

    raise Http404("Vocabulary section not found")


@login_required(login_url='/login/')
def classroom_vocabulary_practice_quiz_start(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)
    if redirect_response:
        return redirect_response
    if role is None:
        return classroom_access_denied(request, classroom=classroom, message='You do not have access to this classroom.')
    if role == 'student' and not get_membership_section_access_map(membership).get('vocabulary'):
        return classroom_access_denied(request, classroom=classroom, message='You do not have access to Vocabulary.')
    return _start_vocabulary_quiz(request, classroom=classroom)


@login_required(login_url='/login/')
def classroom_vocabulary_practice_quiz_result(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)
    if redirect_response:
        return redirect_response
    if role is None:
        return classroom_access_denied(request, classroom=classroom, message='You do not have access to this classroom.')
    if role == 'student' and not get_membership_section_access_map(membership).get('vocabulary'):
        return classroom_access_denied(request, classroom=classroom, message='You do not have access to Vocabulary.')
    return _finish_vocabulary_quiz(request, classroom=classroom)


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
        role='student',
        status='approved'
    )

    membership.status = 'removed'
    membership.approved_at = None
    membership.removed_at = timezone.now()
    membership.left_at = None
    membership.save(update_fields=['status', 'approved_at', 'removed_at', 'left_at'])

    messages.success(request, "Student removed from classroom.")
    return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)


@login_required(login_url='/login/')
@require_POST
def leave_classroom(request, classroom_id):
    membership = get_object_or_404(
        ClassroomMembership,
        classroom_id=classroom_id,
        user=request.user,
        role='student',
        status='approved'
    )

    membership.status = 'left'
    membership.approved_at = None
    membership.left_at = timezone.now()
    membership.removed_at = None
    membership.save(update_fields=['status', 'approved_at', 'left_at', 'removed_at'])

    messages.success(request, "You left the classroom.")
    return redirect('sat_menu')


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

    if not classroom.is_sat_classroom:
        return redirect('classroom_ap_tests', classroom_id=classroom.id)

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

    active_tests, past_tests = _split_tests_by_user_progress(request.user, tests, classroom=classroom)

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
        'show_lessons': False,
        'practice_summary': {
            'available': len(tests),
            'active': len(active_tests),
            'past': len(past_tests),
            'resumable': sum(1 for test in active_tests if test.has_active_attempt),
        },
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

    units = list(VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id'))
    tracking_classroom = classroom if role == 'student' else None

    return render(request, 'sat/vocabulary.html', {
        'units': units,
        'classroom': classroom,
        'summary': get_vocabulary_summary(request.user, classroom=tracking_classroom),
        'unit_rows': build_unit_progress_rows(request.user, classroom=tracking_classroom, units=units),
        'recent_attempts': VocabularyQuizAttempt.objects.filter(user=request.user, classroom=tracking_classroom)[:5],
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


def _build_test_progress_rows(student, tests, classroom=None):
    rows = []
    tests = list(tests)

    if not tests:
        return rows

    test_ids = [test.pk for test in tests]

    modules = TestModule.objects.filter(user=student, test_id__in=test_ids, **_classroom_scope_filter(classroom)).select_related('test').order_by('test_id', '-created_at')
    reviews = TestReview.objects.filter(user=student, test_id__in=test_ids, **_classroom_scope_filter(classroom)).select_related('test').order_by('test_id', '-created_at')
    stages = TestStage.objects.filter(user=student, test_id__in=test_ids, **_classroom_scope_filter(classroom)).select_related('test').order_by('test_id', '-created_at')

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


def _build_test_results_context_for_user(test_obj, user, review_key=None, classroom=None):
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

    _backfill_completed_attempt_reviews(user, test_obj, classroom=classroom)

    attempts = list(TestReview.objects.filter(
        user=user,
        test=test_obj,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at'))

    selected_review = None
    if review_key:
        selected_review = next((attempt for attempt in attempts if attempt.key == review_key), None)
    if not selected_review:
        selected_review = attempts[0] if attempts else None

    attempt_id = _resolve_attempt_id(user, test_obj, selected_review=selected_review, classroom=classroom)
    latest_modules = _load_latest_modules(user, test_obj, attempt_id=attempt_id, classroom=classroom)

    missing_modules = []
    for section, module in required_modules:
        key = f"{section}_{module}"
        if key not in latest_modules:
            missing_modules.append(key)

    status.update(_section_submission_status(required_modules, missing_modules))

    if missing_modules:
        return {
            'is_complete': False,
            'missing_modules': missing_modules,
            'status': status,
            'test_mode': test_mode,
            'has_english': has_english,
            'has_math': has_math,
            'questions': questions,
            'attempts': attempts,
            'attempt_options': _build_review_attempt_options(attempts, selected_review, classroom=classroom),
            'selected_review': selected_review,
            'selected_review_key': selected_review.key if selected_review else '',
            'review_key': review_key,
            'available_slots': {f'{section}_{module}' for section, module in required_modules},
            'has_english_m1': ('english', 'm1') in required_modules,
            'has_english_m2': ('english', 'm2') in required_modules,
            'has_math_m1': ('math', 'm1') in required_modules,
            'has_math_m2': ('math', 'm2') in required_modules,
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
                    is_correct = bool(q_obj and check_english_answer(q_obj, answer.get('answer')))
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

    testreview = selected_review
    if not testreview:
        testreview = TestReview.objects.filter(
            user=user,
            test=test_obj,
            score__isnull=False,
            **_classroom_scope_filter(classroom),
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
        'attempts': attempts,
        'attempt_options': _build_review_attempt_options(attempts, selected_review, classroom=classroom),
        'selected_review': selected_review,
        'selected_review_key': selected_review.key if selected_review else '',
        'review_key': review_key,
        'available_slots': {f'{section}_{module}' for section, module in required_modules},
        'has_english_m1': ('english', 'm1') in required_modules,
        'has_english_m2': ('english', 'm2') in required_modules,
        'has_math_m1': ('math', 'm1') in required_modules,
        'has_math_m2': ('math', 'm2') in required_modules,
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

    allowed_tests = _get_membership_allowed_tests(membership)
    allowed_test_ids = [test.pk for test in allowed_tests]
    total_items = len(allowed_test_ids)
    completed_items = TestReview.objects.filter(
        user=student,
        classroom=classroom,
        test_id__in=allowed_test_ids,
    ).exclude(score__isnull=True).count()
    activity_count = TestModule.objects.filter(
        user=student,
        classroom=classroom,
        test_id__in=allowed_test_ids,
    ).count()
    last_module = TestModule.objects.filter(
        user=student,
        classroom=classroom,
        test_id__in=allowed_test_ids,
    ).order_by('-created_at').first()
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
        return None
    return sync_vocabulary_student_progress(classroom, student)


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
    if not _can_manage_classroom_progress(request.user, classroom):
        return HttpResponseForbidden('You can manage only your own classrooms.')

    memberships = list(
        ClassroomMembership.objects.filter(
            classroom=classroom,
            role='student',
            status='approved',
        )
        .select_related('user')
        .prefetch_related('section_access')
        .order_by('user__first_name', 'user__last_name', 'user__username')
    )

    should_refresh = request.GET.get('refresh') == '1'
    for membership in memberships:
        # Vocabulary is cheap and activity-driven, so keep it live on every load.
        recalculate_vocabulary_progress(classroom, membership.user)
        existing_sections = set(
            StudentProgress.objects.filter(
                classroom=classroom,
                student=membership.user,
            ).values_list('section', flat=True)
        )
        if should_refresh or 'practice_tests' not in existing_sections:
            recalculate_practice_tests_progress(classroom, membership.user)
        if should_refresh or 'admissions' not in existing_sections:
            recalculate_admissions_progress(classroom, membership.user)

    records = StudentProgress.objects.filter(
        classroom=classroom,
        student_id__in=[membership.user_id for membership in memberships],
    ).select_related('student')
    records_by_student = defaultdict(dict)
    for record in records:
        records_by_student[record.student_id][record.section] = record

    now_value = timezone.now()
    rows = []
    for membership in memberships:
        section_map = records_by_student.get(membership.user_id, {})
        practice = section_map.get('practice_tests')
        vocabulary = section_map.get('vocabulary')
        admissions = section_map.get('admissions')
        access_map = get_membership_section_access_map(membership)

        trackable = [
            record for record in (practice, vocabulary)
            if record and record.total_items > 0
        ]
        overall_percent = round(
            sum(float(record.completion_percent) for record in trackable) / len(trackable),
            1,
        ) if trackable else 0
        last_activity = max(
            (record.last_activity_at for record in (practice, vocabulary, admissions) if record and record.last_activity_at),
            default=None,
        )
        is_active_recently = bool(last_activity and last_activity >= now_value - timedelta(days=7))
        needs_attention = (
            not last_activity
            or last_activity < now_value - timedelta(days=14)
            or overall_percent < 30
        )
        rows.append({
            'student': membership.user,
            'membership': membership,
            'practice_tests': practice,
            'vocabulary': vocabulary,
            'admissions': admissions,
            'access_map': access_map,
            'overall_percent': overall_percent,
            'last_activity_at': last_activity,
            'is_active_recently': is_active_recently,
            'needs_attention': needs_attention,
        })

    student_count = len(rows)
    average_overall = round(sum(row['overall_percent'] for row in rows) / student_count, 1) if student_count else 0
    average_vocabulary = round(
        sum(float(row['vocabulary'].completion_percent) if row['vocabulary'] else 0 for row in rows) / student_count,
        1,
    ) if student_count else 0
    active_count = sum(1 for row in rows if row['is_active_recently'])
    attention_count = sum(1 for row in rows if row['needs_attention'])

    return render(request, 'sat/classroom_progress_dashboard.html', {
        'classroom': classroom,
        'grouped_progress': rows,
        'refreshed': should_refresh,
        'dashboard_stats': {
            'student_count': student_count,
            'average_overall': average_overall,
            'average_vocabulary': average_vocabulary,
            'active_count': active_count,
            'attention_count': attention_count,
        },
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
    test_rows = _build_test_progress_rows(student, tests, classroom=classroom)
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
        return HttpResponseForbidden('You can manage only your own classrooms.')

    membership = _get_classroom_student_membership_or_404(classroom, student_id)
    student = membership.user
    summary = sync_vocabulary_student_progress(classroom, student)
    vocab_progress = StudentProgress.objects.filter(
        classroom=classroom,
        student=student,
        section='vocabulary',
    ).first()
    units = list(
        VocabularyUnit.objects.filter(is_active=True)
        .prefetch_related('words')
        .order_by('order', 'id')
    )
    unit_rows = build_unit_progress_rows(student, classroom=classroom, units=units)
    weak_words = get_weak_words(student, classroom=classroom, limit=15)
    recent_attempts = VocabularyQuizAttempt.objects.filter(
        user=student,
        classroom=classroom,
    )[:10]

    return render(request, 'sat/classroom_student_vocab_progress.html', {
        'classroom': classroom,
        'membership': membership,
        'student_obj': student,
        'access_map': get_membership_section_access_map(membership),
        'vocab_progress': vocab_progress,
        'summary': summary,
        'units': units,
        'unit_rows': unit_rows,
        'weak_words': weak_words,
        'recent_attempts': recent_attempts,
        'total_words': summary['total_words'],
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

    review_key = request.GET.get('review_key')
    result_context = _build_test_results_context_for_user(test_obj, student, review_key=review_key, classroom=classroom)
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

    review = TestReview.objects.filter(key=key).select_related('user', 'test', 'makeup_test', 'classroom').first()
    if not review or review.user_id != student.id or review.classroom_id != classroom.id:
        return HttpResponse('This review is no longer available. A new retake may already be in progress.')

    if review.score is None:
        return HttpResponse('Review is unavailable because a retake is currently in progress.')

    module_obj = TestModule.objects.filter(
        test=review.test,
        user=review.user,
        section=section,
        module=module,
        attempt_id=review.attempt_id,
        classroom=classroom,
    ).first()

    if not module_obj:
        return HttpResponse('Review for this section is unavailable because a retake is currently in progress.')
    if not _module_contains_question(module_obj, id):
        raise Http404('This question is not part of the selected attempt module.')

    review_question_model = English_Question if section == 'english' else Math_Question if section == 'math' else None
    if review_question_model:
        prev, answer, new = _review_prev_answer_next(module_obj, review_question_model, id)
    else:
        prev, answer, new = module_obj.find_answer(question_id=id)
    prev = reverse('classroom_student_review_question', args=[classroom.id, student.id, key, section, module, prev]) if prev else ''
    new = reverse('classroom_student_review_question', args=[classroom.id, student.id, key, section, module, new]) if new else ''

    attempts = list(TestReview.objects.filter(
        user=review.user,
        test=review.test,
        score__isnull=False,
        classroom=classroom,
    ).order_by('-created_at'))
    results_url = _review_results_url(review, classroom=classroom, student=student)
    attempt_options = _build_review_attempt_options(
        attempts,
        review,
        section=section,
        module=module,
        question_id=id,
        classroom=classroom,
        student=student,
    )

    if section == 'english':
        question = English_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_eng.html', {
            'question': question,
            'question_payload': _review_question_payload(question, section),
            'review_choices': _review_choices_payload(question, section),
            'answered_choice': '' if question.is_open_text else _normalize_review_choice_letter(answer),
            'correct_choice': '' if question.is_open_text else _normalize_review_choice_letter(question.answer),
            'answered': answer,
            'answer_is_correct': check_english_answer(question, answer),
            'prev': prev,
            'next': new,
            'test': review.test,
            'is_teacher_review': True,
            'classroom': classroom,
            'review_student': student,
            'review': review,
            'results_url': results_url,
            'attempts': attempts,
            'attempt_options': attempt_options,
            'selected_review_key': review.key,
        })

    if section == 'math':
        question = Math_Question.objects.filter(id=id).first()
        if not question:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_math.html', {
            'question': question,
            'question_payload': _review_question_payload(question, section),
            'review_choices': _review_choices_payload(question, section),
            'answered_choice': _normalize_review_choice_letter(answer),
            'correct_choice': _normalize_review_choice_letter(question.answer),
            'answered': answer,
            'answer_is_correct': check_written(answer, question.answer),
            'prev': prev,
            'next': new,
            'test': review.test,
            'is_teacher_review': True,
            'classroom': classroom,
            'review_student': student,
            'review': review,
            'results_url': results_url,
            'attempts': attempts,
            'attempt_options': attempt_options,
            'selected_review_key': review.key,
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
    classroom_type = request.POST.get('classroom_type', classroom.classroom_type).strip().lower()

    if classroom_type not in {Classroom.CLASSROOM_TYPE_SAT, Classroom.CLASSROOM_TYPE_AP}:
        messages.error(request, "Choose a valid classroom type.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    if not name:
        messages.error(request, "Classroom name is required.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    classroom.name = name
    classroom.description = description
    classroom.classroom_type = classroom_type
    classroom.save(update_fields=['name', 'description', 'classroom_type'])

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
    """Return only supported SAT module slots that actually contain questions.

    Older code allowed NULL or arbitrary module values into the sequence.  The UI,
    draft models, scoring, and guest completion logic support only module_1/m1 and
    module_2/m2, so an invalid admin/import value could trap an attempt forever.
    """
    supported = [('module_1', 'm1'), ('module_2', 'm2')]
    sequence = []
    english_modules = set(
        English_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    )
    math_modules = set(
        Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    )
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
    return sequence


def get_makeup_test_sequence(makeup_test):
    """Return only supported Module 1/2 steps in exam order."""
    supported = [('module_1', 'm1'), ('module_2', 'm2')]
    english_modules = set(
        makeup_test.english_questions.filter(module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    )
    math_modules = set(
        makeup_test.math_questions.filter(module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    )
    sequence = []
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
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
        if test_stage.stage == len(sequence):
            test_stage.stage = len(sequence) + 1
            test_stage.save(update_fields=['stage', 'updated_at'])
        return True

    test_stage.stage += 1
    test_stage.save(update_fields=['stage', 'updated_at'])
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

    resumable_stage = _get_resumable_stage(request.user, test, classroom=classroom)
    if resumable_stage:
        return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)

    completed_review = TestReview.objects.filter(
        user=request.user,
        test=test,
        score__isnull=False,
        **_classroom_scope_filter(classroom),
    ).order_by('-created_at').first()

    if completed_review:
        return redirect(_results_url_for_test(test, classroom=classroom, review_key=completed_review.key))

    has_active_attempt = False

    return render(request, 'test/test_modules.html', {
        'test': test,
        'classroom': classroom,
        'role': role,
        'has_active_attempt': has_active_attempt,
        'start_url': reverse('classroom_test', kwargs={
            'classroom_id': classroom.id,
            'pk': test.name
        }),
        **_build_test_start_overview(test, request.user),
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

    test_stage, created = _get_or_create_regular_test_stage(user, test, stage=1, classroom=classroom)

    current_step = get_current_test_step(test_stage)
    if current_step is None:
        return redirect(_results_url_for_test(test, classroom=classroom))

    section, module = current_step

    existing_module = TestModule.objects.filter(
        test=test,
        section=section,
        module=module,
        user=user,
        attempt_id=test_stage.attempt_id,
        classroom=classroom,
    )

    if existing_module.exists():
        finished = advance_test_stage(test_stage)
        if finished:
            return redirect(_results_url_for_test(test, classroom=classroom))
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
                return redirect(_results_url_for_test(test, classroom=classroom))
            return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)

        runtime = _regular_module_runtime(test_stage, section, module, questions, classroom=classroom)
        if runtime['redirect_url']:
            return redirect(runtime['redirect_url'])
        context = {
            'questions': questions,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds,
            'classroom': classroom,
        }
        context.update(runtime['context'])
        return render(request, 'test/test_eng.html', context)

    if section == 'math':
        questions = Math_Question.objects.filter(
            test=test,
            module=f'module_{module[1]}'
        ).order_by('number')

        if not questions.exists():
            finished = advance_test_stage(test_stage)
            if finished:
                return redirect(_results_url_for_test(test, classroom=classroom))
            return redirect('classroom_test', classroom_id=classroom.id, pk=test.name)

        runtime = _regular_module_runtime(test_stage, section, module, questions, classroom=classroom)
        if runtime['redirect_url']:
            return redirect(runtime['redirect_url'])

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
        context = {
            'questions': questions,
            'questions_data': questions_data,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds,
            'classroom': classroom,
        }
        context.update(runtime['context'])
        return render(request, 'test/test_math.html', context)

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
def classroom_ap_tests(request, classroom_id):
    classroom, role, membership, redirect_response = resolve_classroom_and_role(request, classroom_id)

    if redirect_response:
        return redirect_response

    if role is None:
        return classroom_access_denied(
            request,
            classroom=classroom,
            message="You do not have access to this classroom."
        )

    if not classroom.is_ap_classroom:
        messages.error(request, "This is a SAT classroom. Open SAT tests instead.")
        if role == 'student':
            return redirect('student_classroom_home', classroom_id=classroom.id)
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    if APExamEvent is None:
        messages.error(request, "AP tests are not available in this installation.")
        if role == 'student':
            return redirect('student_classroom_home', classroom_id=classroom.id)
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    events = APExamEvent.objects.select_related(
        'exam',
        'exam__ap_class',
    ).filter(
        classrooms=classroom,
        is_public=True,
    ).distinct().order_by('-created_at')

    if role == 'student':
        events = events.filter(exam__status='published')
        events = [event for event in events if event.user_can_see(request.user)]

    return render(request, 'sat/classroom_ap_tests.html', {
        'classroom': classroom,
        'events': events,
        'role': role,
        'membership': membership,
    })


@login_required(login_url='/login/')
def update_classroom_ap_test_access(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    if not classroom.is_ap_classroom:
        messages.error(request, "AP tests can be managed only for AP classrooms.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    if APExamEvent is None:
        messages.error(request, "AP tests are not available in this installation.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    events = list(
        APExamEvent.objects.select_related('exam', 'exam__ap_class')
        .filter(is_public=True)
        .order_by('-created_at')
    )

    if request.method == 'POST':
        selected_event_ids = set(request.POST.getlist('events'))
        selected_events = [event for event in events if str(event.pk) in selected_event_ids]
        classroom.ap_exam_events.set(selected_events)
        messages.success(request, f"AP tests updated for {classroom.name}.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    selected_event_ids = set(str(pk) for pk in classroom.ap_exam_events.values_list('pk', flat=True))

    return render(request, 'sat/update_classroom_ap_test_access.html', {
        'classroom': classroom,
        'events': events,
        'selected_event_ids': selected_event_ids,
    })


@login_required(login_url='/login/')
def update_classroom_practice_test_access(request, classroom_id):
    """Save a persistent classroom SAT-test policy and sync current students."""
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

    if not classroom.is_sat_classroom:
        messages.error(request, "SAT tests can be managed only for SAT classrooms.")
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

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

    policy = ClassroomPracticeTestAccessPolicy.objects.filter(classroom=classroom).first()
    if policy:
        access_mode = policy.access_mode
        if access_mode == ClassroomPracticeTestAccessPolicy.ACCESS_MODE_ALL:
            selected_test_ids = set(all_test_ids)
        else:
            selected_test_ids = set(
                str(pk) for pk in policy.selected_tests.values_list('pk', flat=True)
            )
    else:
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

    if request.method == 'POST':
        access_mode = request.POST.get('access_mode', 'selected')
        selected_test_ids = set(request.POST.getlist('tests'))
        if access_mode not in {'all', 'selected'}:
            access_mode = 'selected'

        if access_mode == 'selected' and not selected_test_ids:
            messages.error(request, "Select at least one practice test.")
            return render(request, 'sat/update_classroom_practice_test_access.html', {
                'classroom': classroom,
                'tests': tests,
                'eligible_count': len(eligible_memberships),
                'total_students_count': len(memberships),
                'selected_test_ids': selected_test_ids,
                'access_mode': 'selected',
                'has_saved_policy': bool(policy),
            })

        policy, _ = ClassroomPracticeTestAccessPolicy.objects.update_or_create(
            classroom=classroom,
            defaults={'access_mode': access_mode},
        )

        if access_mode == 'all':
            policy.selected_tests.clear()
            selected_tests = tests
            selected_test_ids = set(all_test_ids)
        else:
            selected_tests = [test for test in tests if str(test.pk) in selected_test_ids]
            policy.selected_tests.set(selected_tests)

        membership_ids = [membership.id for membership in eligible_memberships]
        if membership_ids:
            StudentPracticeTestAccess.objects.filter(
                membership_id__in=membership_ids
            ).delete()

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

        mode_label = (
            'all practice tests'
            if access_mode == 'all'
            else f'{len(selected_tests)} selected practice test(s)'
        )
        messages.success(
            request,
            f"Classroom default saved: {mode_label}. Applied to {len(eligible_memberships)} "
            "current student(s); future approved students will inherit it automatically."
        )
        return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

    return render(request, 'sat/update_classroom_practice_test_access.html', {
        'classroom': classroom,
        'tests': tests,
        'eligible_count': len(eligible_memberships),
        'total_students_count': len(memberships),
        'selected_test_ids': selected_test_ids,
        'access_mode': access_mode,
        'has_saved_policy': bool(policy),
    })
