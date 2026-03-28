from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, HttpResponseRedirect, Http404, JsonResponse
from apps.base.decorators import allowed_users
from django.contrib.auth.models import Group, User
from django.contrib.auth.decorators import login_required
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

def custom_round(number, base=0.4):
    if number % 1 >= base:
        return ceil(number)
    else:
        return floor(number)


def restart(request, pk):
    user = request.user        
    test = Test.objects.filter(name=pk)[0]

    if is_member(user, ['OFFLINE', 'Admin']):
        stage = TestStage.objects.filter(user=user, test=test)[0]
        review = TestReview.objects.filter(user=user, test=test)[0]
        review.score = None
        review.save()
        response = stage.resolve()
        if response:
            return render(request, 'sat/restart_success.html', {
                'test_name': pk,
                'section': None
            })
        else:
            # Get user group name for display
            user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'
            
            return render(request, 'sat/retake_limit_exceeded.html', {
                'test_name': pk,
                'section': None,
                'retakes_used': stage.retake_count,
                'max_retakes': stage.get_max_retakes(),
                'user_group': user_group
            })
    return HttpResponse("you are not offline user")


def check_written(response, answer):
    if response is None or answer is None:
        return False

    response = str(response).strip()
    answer = str(answer).strip()

    if not response or not answer:
        return False

    responses = response.replace(' ', '').split(',')
    answers = answer.replace(' ', '').split(',')

    responses = [item for item in responses if item != '']
    answers = [item for item in answers if item != '']

    if not responses or not answers:
        return False

    for res in responses:
        for ans in answers:
            if res == ans:
                return True

    return False


@allowed_users(['Admin', 'Tester'])
def tester_view(request):
    tests = Test.objects.all()
    return render(request, 'test/dashboard.html', {'tests': tests})


def is_member(user, names):
    for name in names:
        if user.groups.filter(name=name).exists():
            return True
    return False


# Create your views here.

@login_required(login_url='/login/')
def practice_tests(request):
    user = request.user
    user_groups = user.groups.all()

    tests = Test.objects.filter(groups__in=user_groups).distinct()

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

    active_tests = []
    past_tests = []

    for test in tests:
        if TestReview.objects.filter(test=test, user=user).exists():
            review = TestReview.objects.filter(test=test, user=user)[0]
            if review.score == 0 or review.score is None:
                active_tests.append(test)
            else:
                past_tests.append(test)
        else:
            active_tests.append(test)

    purchased_packages = PurchasedLessonPackage.objects.filter(user=user)
    if purchased_packages.exists():
        lessons = Lesson.objects.filter(package__in=[p.package for p in purchased_packages])
        active_lessons = []
        past_lessons = []

        for lesson in lessons:
            lp = LessonProgress.objects.filter(user=user, lesson=lesson).first()
            if lp and lp.completed:
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

def check_the_answers(request):
    if request.method == "POST":
        json_response = json.loads(request.body.decode('utf-8'))
        test_type = json_response.get('test_type', 'regular')
        
        if test_type == 'regular':
            test = Test.objects.get(name=json_response['test'])
            makeup_test = None
        elif test_type == 'makeup':
            test = None
            makeup_test = MakeupTest.objects.get(name=json_response['test'])
        
        section = json_response['section']
        module = json_response['module']
        
        submission_data = request.body.decode('utf-8')
        
        # Use get_or_create to prevent race conditions and ensure no duplicates
        test_module, created = TestModule.objects.get_or_create(
            test=test,
            makeup_test=makeup_test,
            section=section,
            module=module,
            user=request.user,
            test_type=test_type,
            defaults={'answers': submission_data}
        )
        
        # If the record already existed, update the answers
        if not created:
            test_module.answers = submission_data
            test_module.save()
        
        return HttpResponse('200 success', status=200)
    return HttpResponse('invalid call')


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

    test_mode = get_test_mode(test_obj)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    required_modules = []
    if has_english:
        required_modules.extend([('english', 'm1'), ('english', 'm2')])
    if has_math:
        required_modules.extend([('math', 'm1'), ('math', 'm2')])

    latest_modules = {}
    all_modules_query = TestModule.objects.filter(user=user, test=test_obj).order_by('-created_at')

    for module in all_modules_query:
        key = f"{module.section}_{module.module}"
        if key not in latest_modules:
            latest_modules[key] = module

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

    for module in modules_to_process:
        try:
            answers_list = json.loads(module.answers or '{}').get('answers', [])
        except Exception:
            answers_list = []

        sec = module.section
        mod = module.module

        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0) or 0)
                time_spent_totals[sec][mod] += time_spent

                if sec == 'english':
                    q_obj = English_Question.objects.get(id=int(answer['questionID']))
                    is_correct = (answer.get('answer') == q_obj.answer)
                else:
                    q_obj = Math_Question.objects.get(id=int(answer['questionID']))
                    raw_answer = answer.get('answer')
                    is_correct = (raw_answer is not None and check_written(raw_answer, q_obj.answer))

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

    if test_mode == 'full':
        score = calculator.get_total(
            correct_counts['english']['m1'],
            correct_counts['english']['m2'],
            correct_counts['math']['m1'],
            correct_counts['math']['m2']
        )
    elif test_mode == 'ebrw_only':
        english_score = correct_counts['english']['m1'] + correct_counts['english']['m2']
        score = {
            'total': english_score,
            'sections': {
                'english': {'score': english_score, 'range': {'lower': 0, 'upper': english_score}},
                'math': None,
            }
        }
    elif test_mode == 'math_only':
        math_score = correct_counts['math']['m1'] + correct_counts['math']['m2']
        score = {
            'total': math_score,
            'sections': {
                'english': None,
                'math': {'score': math_score, 'range': {'lower': 0, 'upper': math_score}},
            }
        }
    else:
        score = {
            'total': 0,
            'sections': {
                'english': None,
                'math': None,
            }
        }

    key = 'default'
    testreview, created = TestReview.objects.get_or_create(user=user, test=test_obj)
    if created:
        testreview.update_key()
        if user.groups.filter(name='OFFLINE').exists():
            testreview.duration = timedelta(days=3)
            testreview.save()

    key = testreview.key
    testreview.score = score['total'] if isinstance(score, dict) else 0
    testreview.save()

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
    })

    

@login_required(login_url='/login/')
def start_Practise(request, pk):
    user = request.user

    # единая логика доступа: админ/стaff/суперюзер или группа Admin/Tester
    is_admin_like = (
        user.is_superuser
        or user.is_staff
        or is_member(user, ['Admin', 'Tester'])
    )

    if is_admin_like:
        test_qs = Test.objects.filter(name=pk)
    else:
        user_groups = user.groups.all()
        test_qs = Test.objects.filter(name=pk, groups__in=user_groups).distinct()

    test = test_qs.first()
    if not test:
        return HttpResponse(f"Test '{pk}' is not found or not assigned to your account.", status=404)

    test_stage = TestStage.objects.filter(user=user, test=test)
    if test_stage.exists():
        return redirect('test', pk=test.name)

    return render(request, 'test/test_modules.html', {'test': test})


@login_required(login_url='/login/')
def question(request, key, section, module, id):
    try:
        group = Group.objects.get(name='OFFLINE')
    except Group.DoesNotExist:
        # If OFFLINE group doesn't exist, create it
        group = Group.objects.create(name='OFFLINE')
    try:
        test = TestReview.objects.get(key=key)
        if not test.is_active():
            # Check if user is not in OFFLINE or Admin groups
            if not (group in request.user.groups.all() or request.user.groups.filter(name='Admin').exists()):
                # Format dates for display
                review_started = test.created_at.strftime('%B %d, %Y at %I:%M %p')
                review_duration = str(test.duration)
                expired_time = (test.created_at + test.duration).strftime('%B %d, %Y at %I:%M %p')
                
                return render(request, 'sat/review_time_over.html', {
                    'test_name': test.test.name if test.test else (test.makeup_test.name if test.makeup_test else 'Unknown'),
                    'review_started': review_started,
                    'review_duration': review_duration,
                    'expired_time': expired_time
                })
    except:
        return HttpResponse('Invalid Key')
    prev, answer, new = TestModule.objects.get(test=test.test, user=test.user, section=section, module=module).find_answer(question_id=id)
    prev = f'/sat/question/{key}/{section}/{module}/{prev}' if prev else ''
    new = f'/sat/question/{key}/{section}/{module}/{new}' if new else ''
    if section == 'english':
        try:
            question = English_Question.objects.filter(id=id)[0]
        except:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_eng.html', {'question': question, 'answered': answer, 'prev': prev, 'next': new, 'test': test.test})

    if section == 'math':
        try:
            question = Math_Question.objects.filter(id=id)[0]
        except:
            return HttpResponse('Question is not found!')
        return render(request, 'test/review/test_math.html', {'question': question, 'answered': answer, 'prev': prev, 'next': new, 'test': test.test})


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
    try:
        makeup_test = MakeupTest.objects.filter(name=pk, groups__in=user_groups).distinct()[0]
    except MakeupTest.DoesNotExist:
        return HttpResponse('Permission Error')

    test_stage, created = TestStage.objects.get_or_create(
        user=user,
        makeup_test=makeup_test,
        test_type='makeup',
        defaults={'stage': 1}
    )

    test, section, module = test_stage.get_models()
    m = TestModule.objects.filter(makeup_test=makeup_test, section=section, module=module, user=user, test_type='makeup')
    if m.exists():
        if test_stage.next_stage():
            return redirect('makeup_results', pk=makeup_test.name)
        return makeup_test_module(request, pk=makeup_test.name)

    if section == 'english':
        questions = makeup_test.get_module_questions(section, f'module_{module[1]}')
        if questions.exists():
            return render(request, 'test/makeup_eng.html', {
                'questions': questions,
                'module': module,
                'test': makeup_test,
                'section': section,
                'is_makeup': True
            })
    elif section == 'math':
        questions = makeup_test.get_module_questions(section, f'module_{module[1]}')
        if questions.exists():
            return render(request, 'test/test_math.html', {
                'questions': questions,
                'module': module,
                'test': makeup_test,
                'section': section,
                'is_makeup': True
            })

    return HttpResponse("No questions available for this module")


@login_required(login_url='/login/')
def module_test(request, pk):
    user = request.user
    user_groups = request.user.groups.all()

    try:
        test = Test.objects.filter(name=pk, groups__in=user_groups).distinct()[0]
    except Exception:
        return HttpResponse('Permission Error')

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
        return redirect('results', test=test)

    section, module = current_step

    existing_module = TestModule.objects.filter(
        test=test,
        section=section,
        module=module,
        user=user
    )

    if existing_module.exists():
        finished = advance_test_stage(test_stage)
        if finished:
            return redirect('results', test=test)
        return module_test(request, pk=test.pk)

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
                return redirect('results', test=test)
            return module_test(request, pk=test.pk)

        return render(request, 'test/test_eng.html', {
            'questions': questions,
            'module': module,
            'test': test,
            'section': section,
            'custom_time_seconds': custom_time_seconds
        })

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

    required_modules = []
    if has_english:
        required_modules.extend([('english', 'm1'), ('english', 'm2')])
    if has_math:
        required_modules.extend([('math', 'm1'), ('math', 'm2')])

    latest_modules = {}
    all_modules_query = TestModule.objects.filter(user=user, test=test_obj).order_by('-created_at')

    for module in all_modules_query:
        key = f"{module.section}_{module.module}"
        if key not in latest_modules:
            latest_modules[key] = module

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

    for module in modules_to_process:
        try:
            answers_list = json.loads(module.answers or '{}').get('answers', [])
        except Exception:
            answers_list = []

        sec = module.section
        mod = module.module

        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue

        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0) or 0)
                time_spent_totals[sec][mod] += time_spent

                if sec == 'english':
                    q_obj = English_Question.objects.get(id=int(answer['questionID']))
                    is_correct = (answer.get('answer') == q_obj.answer)
                    display_answer = answer.get('answer')
                else:
                    q_obj = Math_Question.objects.get(id=int(answer['questionID']))
                    raw_answer = answer.get('answer')
                    is_correct = (raw_answer is not None and check_written(raw_answer, q_obj.answer))
                    display_answer = raw_answer.replace('/', '-') if raw_answer else raw_answer

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

    if test_mode == 'full':
        score = calculator.get_total(
            correct_counts['english']['m1'],
            correct_counts['english']['m2'],
            correct_counts['math']['m1'],
            correct_counts['math']['m2']
        )
    elif test_mode == 'ebrw_only':
        english_score = correct_counts['english']['m1'] + correct_counts['english']['m2']
        score = {
            'total': english_score,
            'sections': {
                'english': {'score': english_score, 'range': {'lower': 0, 'upper': english_score}},
                'math': None,
            }
        }
    elif test_mode == 'math_only':
        math_score = correct_counts['math']['m1'] + correct_counts['math']['m2']
        score = {
            'total': math_score,
            'sections': {
                'english': None,
                'math': {'score': math_score, 'range': {'lower': 0, 'upper': math_score}},
            }
        }
    else:
        score = {
            'total': 0,
            'sections': {
                'english': None,
                'math': None,
            }
        }

    testreview, created = TestReview.objects.get_or_create(user=user, test=test_obj)
    if created:
        testreview.update_key()
        if user.groups.filter(name='OFFLINE').exists():
            testreview.duration = timedelta(days=3)
            testreview.save()

    key = testreview.key
    testreview.score = score['total']
    testreview.save()

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
        'key': key,
        'questions': questions,
        'test_mode': test_mode,
        'has_english': has_english,
        'has_math': has_math,
    })




@login_required(login_url='login')
def certificate(request, test):
    test = Test.objects.get(pk=test)
    user = request.user
    testreview = TestReview.objects.filter(user=user, test=test).first()

    if not testreview:
        return HttpResponse("Invalid TEST review contact tech@sat800makon.uz")

    test_mode = get_test_mode(test)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    if testreview.exists if hasattr(testreview, 'exists') else False:
        pass

    response = testreview.check_and_update_domains()
    if not testreview.domains:
        return HttpResponse('Domains are not entered to this practise questions')

    if testreview.certificate != '':
        try:
            if testreview.certificate.startswith('certificates/'):
                from apps.sat.storages import PrivateStorage
                storage = PrivateStorage()
                signed_url = storage.url(testreview.certificate)
                return HttpResponseRedirect(signed_url)
            else:
                return FileResponse(open(testreview.certificate, 'rb'), content_type='application/pdf')
        except Exception:
            pass

    questions = {
        'wrongs': {
            "Information and Ideas": 0,
            "Craft and Structure": 0,
            "Expression of Ideas": 0,
            "Standard English Conventions": 0,
            "Algebra": 0,
            "Advanced Math": 0,
            "Problem-Solving and Data Analysis": 0,
            "Geometry and Trigonometry": 0
        },
        'total': {
            "Information and Ideas": 0,
            "Craft and Structure": 0,
            "Expression of Ideas": 0,
            "Standard English Conventions": 0,
            "Algebra": 0,
            "Advanced Math": 0,
            "Problem-Solving and Data Analysis": 0,
            "Geometry and Trigonometry": 0
        }
    }

    a = e = l = u = 0

    if has_english:
        english_modules = TestModule.objects.filter(user=user, test=test, section='english')
        eng_m1 = english_modules.filter(module='m1').first()
        eng_m2 = english_modules.filter(module='m2').first()

        if eng_m1:
            for question in json.loads(eng_m1.answers or '{}').get('answers', []):
                try:
                    db_question = English_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] == db_question.answer:
                        a += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

        if eng_m2:
            for question in json.loads(eng_m2.answers or '{}').get('answers', []):
                try:
                    db_question = English_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] == db_question.answer:
                        e += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

    if has_math:
        math_modules = TestModule.objects.filter(user=user, test=test, section='math')
        math_m1 = math_modules.filter(module='m1').first()
        math_m2 = math_modules.filter(module='m2').first()

        if math_m1:
            for question in json.loads(math_m1.answers or '{}').get('answers', []):
                try:
                    db_question = Math_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] is None:
                        questions['wrongs'][db_question.domain.name] += 1
                        continue
                    if check_written(question['answer'], db_question.answer):
                        l += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

        if math_m2:
            for question in json.loads(math_m2.answers or '{}').get('answers', []):
                try:
                    db_question = Math_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] is None:
                        questions['wrongs'][db_question.domain.name] += 1
                        continue
                    if check_written(question['answer'], db_question.answer):
                        u += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

    if test_mode == 'full':
        score = calculator.get_total(a, e, l, u)
    elif test_mode == 'ebrw_only':
        english_score = a + e
        score = {
            'total': english_score,
            'range_total': {'lower': 0, 'upper': english_score},
            'sections': {
                'english': {'score': english_score, 'range': {'lower': 0, 'upper': english_score}},
                'math': {'score': 0, 'range': {'lower': 0, 'upper': 0}},
            }
        }
    elif test_mode == 'math_only':
        math_score = l + u
        score = {
            'total': math_score,
            'range_total': {'lower': 0, 'upper': math_score},
            'sections': {
                'english': {'score': 0, 'range': {'lower': 0, 'upper': 0}},
                'math': {'score': math_score, 'range': {'lower': 0, 'upper': math_score}},
            }
        }
    else:
        return HttpResponse("No valid questions found for certificate")

    code = testreview.key
    path = BASE_DIR

    counts = [7, 7, 7, 7, 7, 7, 7, 7]
    wrongs = list(questions['wrongs'].values())
    totals = list(questions['total'].values())

    for i in range(4):
        factor = wrongs[i] // 2
        if factor >= 7:
            counts[i] = 0
            continue
        counts[i] -= factor

    for i in range(4, 8):
        if totals[i] > 0:
            counts[i] = custom_round((totals[i] - wrongs[i]) / totals[i] * 7)
        else:
            counts[i] = 0

    detials = {
        "t-sc": str(score['total']),
        "t-rs": f"{score['range_total']['lower']}-{score['range_total']['upper']}",
        "full_name": user.username,
        "test_name": test.name,
        "test_date": str(testreview.created_at)[:11],
        "r-sc": str(score['sections']['english']['score']),
        "r-rs": f"{score['sections']['english']['range']['lower']}-{score['sections']['english']['range']['upper']}",
        "m-sc": str(score['sections']['math']['score']),
        "m-rs": f"{score['sections']['math']['range']['lower']}-{score['sections']['math']['range']['upper']}"
    }

    output = create_certificate(detials, code, path, counts)
    testreview.certificate = output
    testreview.save()

    from apps.sat.storages import PrivateStorage
    storage = PrivateStorage()
    signed_url = storage.url(testreview.certificate)
    return HttpResponseRedirect(signed_url)



@allowed_users(['Admin'])
def certificate_by_user(request, test, username):
    test = Test.objects.get(pk=test)
    user = User.objects.get(username=username)
    testreview = TestReview.objects.filter(user=user, test=test).first()

    if not testreview:
        return HttpResponse("Invalid TEST review contact tech@sat800makon.uz")

    test_mode = get_test_mode(test)
    has_english = test_mode in ['full', 'ebrw_only']
    has_math = test_mode in ['full', 'math_only']

    testreview.check_and_update_domains()
    if not testreview.domains:
        return HttpResponse('Domains are not entered to this practise questions')

    questions = {
        'wrongs': {
            "Information and Ideas": 0,
            "Craft and Structure": 0,
            "Expression of Ideas": 0,
            "Standard English Conventions": 0,
            "Algebra": 0,
            "Advanced Math": 0,
            "Problem-Solving and Data Analysis": 0,
            "Geometry and Trigonometry": 0
        },
        'total': {
            "Information and Ideas": 0,
            "Craft and Structure": 0,
            "Expression of Ideas": 0,
            "Standard English Conventions": 0,
            "Algebra": 0,
            "Advanced Math": 0,
            "Problem-Solving and Data Analysis": 0,
            "Geometry and Trigonometry": 0
        }
    }

    a = e = l = u = 0

    if has_english:
        english_modules = TestModule.objects.filter(user=user, test=test, section='english')
        eng_m1 = english_modules.filter(module='m1').first()
        eng_m2 = english_modules.filter(module='m2').first()

        if eng_m1:
            for question in json.loads(eng_m1.answers or '{}').get('answers', []):
                try:
                    db_question = English_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] == db_question.answer:
                        a += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

        if eng_m2:
            for question in json.loads(eng_m2.answers or '{}').get('answers', []):
                try:
                    db_question = English_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] == db_question.answer:
                        e += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

    if has_math:
        math_modules = TestModule.objects.filter(user=user, test=test, section='math')
        math_m1 = math_modules.filter(module='m1').first()
        math_m2 = math_modules.filter(module='m2').first()

        if math_m1:
            for question in json.loads(math_m1.answers or '{}').get('answers', []):
                try:
                    db_question = Math_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] is None:
                        questions['wrongs'][db_question.domain.name] += 1
                        continue
                    if check_written(question['answer'], db_question.answer):
                        l += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

        if math_m2:
            for question in json.loads(math_m2.answers or '{}').get('answers', []):
                try:
                    db_question = Math_Question.objects.get(id=question['questionID'])
                    questions['total'][db_question.domain.name] += 1
                    if question['answer'] is None:
                        questions['wrongs'][db_question.domain.name] += 1
                        continue
                    if check_written(question['answer'], db_question.answer):
                        u += 1
                    else:
                        questions['wrongs'][db_question.domain.name] += 1
                except Exception:
                    continue

    if test_mode == 'full':
        score = calculator.get_total(a, e, l, u)
    elif test_mode == 'ebrw_only':
        english_score = a + e
        score = {
            'total': english_score,
            'range_total': {'lower': 0, 'upper': english_score},
            'sections': {
                'english': {'score': english_score, 'range': {'lower': 0, 'upper': english_score}},
                'math': {'score': 0, 'range': {'lower': 0, 'upper': 0}},
            }
        }
    elif test_mode == 'math_only':
        math_score = l + u
        score = {
            'total': math_score,
            'range_total': {'lower': 0, 'upper': math_score},
            'sections': {
                'english': {'score': 0, 'range': {'lower': 0, 'upper': 0}},
                'math': {'score': math_score, 'range': {'lower': 0, 'upper': math_score}},
            }
        }
    else:
        return HttpResponse("No valid questions found for certificate")

    code = testreview.key
    path = BASE_DIR

    counts = [7, 7, 7, 7, 7, 7, 7, 7]
    wrongs = list(questions['wrongs'].values())
    totals = list(questions['total'].values())

    for i in range(4):
        factor = wrongs[i] // 2
        if factor >= 7:
            counts[i] = 0
            continue
        counts[i] -= factor

    for i in range(4, 8):
        if totals[i] > 0:
            counts[i] = custom_round((totals[i] - wrongs[i]) / totals[i] * 7)
        else:
            counts[i] = 0

    detials = {
        "t-sc": str(score['total']),
        "t-rs": f"{score['range_total']['lower']}-{score['range_total']['upper']}",
        "full_name": user.username,
        "test_name": test.name,
        "test_date": str(testreview.created_at)[:11],
        "r-sc": str(score['sections']['english']['score']),
        "r-rs": f"{score['sections']['english']['range']['lower']}-{score['sections']['english']['range']['upper']}",
        "m-sc": str(score['sections']['math']['score']),
        "m-rs": f"{score['sections']['math']['range']['lower']}-{score['sections']['math']['range']['upper']}"
    }

    output = create_certificate(detials, code, path, counts)
    testreview.certificate = output
    testreview.save()

    from apps.sat.storages import PrivateStorage
    storage = PrivateStorage()
    signed_url = storage.url(testreview.certificate)
    return HttpResponseRedirect(signed_url)


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

        code = ''.join(code_digits)

        # Validate the code
        if not code or len(code) != 6 or not code.isdigit():
            messages.error(request, "Please enter a valid 6-digit code using numbers only.")
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
                messages.error(request, "Invalid secret code. Please try again.")

    return render(request, 'sat/enter_code.html', {})


@login_required(login_url='login')
def restart_section(request, pk, section):
    user = request.user
    test = Test.objects.filter(name=pk).first()

    if not test:
        return HttpResponse("Test not found")

    if is_member(user, ['OFFLINE', 'Admin']):
        stage = TestStage.objects.filter(user=user, test=test).first()
        if not stage:
            return HttpResponse("Test stage not found")

        response = stage.resolve_section(section)
        if response:
            testreview = TestReview.objects.filter(user=user, test=test).first()
            if testreview:
                testreview.score = None
                testreview.save()

            return render(request, 'sat/restart_success.html', {
                'test_name': pk,
                'section': section
            })
        else:
            user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'

            return render(request, 'sat/retake_limit_exceeded.html', {
                'test_name': pk,
                'section': section,
                'retakes_used': stage.retake_count,
                'max_retakes': stage.get_max_retakes(),
                'user_group': user_group
            })

    return HttpResponse("You do not have permission to restart sections")


@login_required(login_url='/login/')
def vocabulary(request):
    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary.html', {
        'units': units
    })


@login_required(login_url='/login/')
def admissions(request):

    return render(request, 'sat/admissions.html', {
        'sections': ADMISSIONS_SECTIONS
    })


@login_required(login_url='/login/')
def vocabulary_section(request, slug):

    if slug == 'word_lists':
        units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')
        return render(request, 'sat/vocabulary_word_lists.html', {
            'units': units
        })

    if slug == 'flashcards':
        units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')
        return render(request, 'sat/vocabulary_flashcards.html', {
            'units': units
        })

    raise Http404("Vocabulary section not found")


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
    return render(request, 'sat/admissions.html', {
        'sections': ADMISSIONS_SECTIONS
    })


@login_required(login_url='/login/')
def admissions_section(request, slug):

    section = ADMISSIONS_SECTIONS.get(slug)
    if not section:
        raise Http404("Admissions section not found")

    return render(request, 'sat/admissions_section.html', {
        'slug': slug,
        'section': section,
    })

@login_required(login_url='/login/')
def vocabulary_practice_quiz(request):

    units = VocabularyUnit.objects.filter(is_active=True).prefetch_related('words').order_by('order', 'id')

    return render(request, 'sat/vocabulary_practice_quiz.html', {
        'units': units
    })

@login_required(login_url='/login/')
def vocabulary_practice_quiz_start(request):

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

    if request.method != 'POST':
        return redirect('vocabulary_practice_quiz')

    questions = request.session.get('vocab_quiz_questions', [])
    score = 0
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
        })

    return render(request, 'sat/vocabulary_practice_quiz_result.html', {
        'results': results,
        'score': score,
        'total': len(questions),
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
        or user.groups.filter(name='teacher').exists()
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
        try:
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

            if access_mode == 'selected':
                selected_tests = Test.objects.filter(pk__in=selected_test_names).distinct()

                for test in selected_tests:
                    StudentPracticeTestAccess.objects.update_or_create(
                        membership=membership,
                        test=test,
                        defaults={'has_access': True}
                    )

            messages.success(request, "Student practice test access updated successfully.")
            return redirect('teacher_classroom_dashboard', classroom_id=classroom.id)

        except Exception as e:
            print("ERROR in update_student_practice_test_access:", repr(e))
            raise

    existing_items = StudentPracticeTestAccess.objects.filter(
        membership=membership,
        has_access=True
    )

    selected_test_names = set(existing_items.values_list('test_id', flat=True))
    access_mode = 'selected' if existing_items.exists() else 'all'

    return render(request, 'sat/update_student_practice_test_access.html', {
        'classroom': classroom,
        'membership': membership,
        'tests': tests,
        'selected_test_names': selected_test_names,
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
def remove_student_from_classroom(request, classroom_id, user_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if classroom.teacher != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You can manage only your own classrooms.")

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

    if role == 'student':
        access_map = get_membership_section_access_map(membership)
        if not access_map.get('practice_tests'):
            return classroom_access_denied(
                request,
                classroom=classroom,
                message="You do not have access to Practice Tests."
            )

        tests = get_student_allowed_practice_tests_queryset(membership)

    else:
        tests = Test.objects.all().distinct()

    def get_day_number(test):
        try:
            name = test.name.strip().lower()
            if name.startswith('day'):
                return int(name.replace('day', '').strip())
            return 999999
        except Exception:
            return 999999

    tests = sorted(tests, key=lambda t: (get_day_number(t), t.name))

    context = {
        'active_tests': tests,
        'past_tests': [],
        'classroom': classroom,
        'is_teacher_view': role in ['teacher', 'admin'],
        'purchased': False,
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

    return admissions(request)

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
    })

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
        definition = request.POST.get('definition', '').strip()
        example = request.POST.get('example', '').strip()

        if not word:
            messages.error(request, "Word is required.")
            return redirect('create_vocabulary_word', unit_id=unit.id)

        if not definition:
            messages.error(request, "Definition is required.")
            return redirect('create_vocabulary_word', unit_id=unit.id)

        VocabularyWord.objects.create(
            unit=unit,
            word=word,
            definition=definition,
            example=example,
        )

        messages.success(request, "Vocabulary word added successfully.")
        return redirect('teacher_vocabulary_unit_detail', unit_id=unit.id)

    return render(request, 'sat/create_vocabulary_word.html', {
        'unit': unit,
    })


@login_required(login_url='/login/')
def create_vocabulary_question(request, unit_id):
    if not is_teacher(request.user):
        return HttpResponseForbidden("Only teachers can add vocabulary questions.")

    unit = get_object_or_404(VocabularyUnit, id=unit_id)

    if request.method == 'POST':
        question_text = request.POST.get('question', '').strip()
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        correct_answer = request.POST.get('correct_answer', '').strip().upper()

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
    custom_access_items = StudentPracticeTestAccess.objects.filter(membership=membership)

    if not custom_access_items.exists():
        return Test.objects.all().distinct()

    allowed_test_names = custom_access_items.filter(
        has_access=True
    ).values_list('test_id', flat=True)

    return Test.objects.filter(pk__in=allowed_test_names).distinct()

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
    mode = get_test_mode(test)

    if mode == 'full':
        return [
            ('english', 'm1'),
            ('english', 'm2'),
            ('math', 'm1'),
            ('math', 'm2'),
        ]
    if mode == 'ebrw_only':
        return [
            ('english', 'm1'),
            ('english', 'm2'),
        ]
    if mode == 'math_only':
        return [
            ('math', 'm1'),
            ('math', 'm2'),
        ]
    return []


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

