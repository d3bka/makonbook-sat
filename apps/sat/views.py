from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, HttpResponseRedirect
from apps.base.decorators import allowed_users
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.conf import settings
from satmakon.settings import BASE_DIR
from .libs import calculator
import json
from django.utils import timezone
from datetime import timedelta
from .libs.certificate.certificate import create_certificate
from math import floor, ceil
from django.contrib import messages  # Added for user feedback
from apps.base.models import UserProfile

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


def check_written(answer: str, response: str):
    answer = answer.strip().replace(' ', '')
    responses = response.strip().replace(' ', '').split(',')
    for response in responses:
        if answer == response:
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
            return int(test.name[3:])
        except Exception:
            return 0

    tests = sorted(tests, key=get_day_number)

    active_tests = []
    past_tests = []

    for test in tests:
        if TestReview.objects.filter(test=test, user=user).exists():
            review = TestReview.objects.filter(test=test, user=user)[0]
            if review.score == 0:
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
    
    # Get all test modules for the given test (both English and Math)
    # Filter to ensure we get exactly one module for each section/module combination
    latest_modules = {}
    
    # Get all modules and organize by section/module combination
    all_modules_query = TestModule.objects.filter(user=user, test=test_obj).order_by('-created_at')
    
    # Take only the latest module for each section/module combination
    for module in all_modules_query:
        key = f"{module.section}_{module.module}"
        if key not in latest_modules:
            latest_modules[key] = module
    
    # Convert dictionary values to a list for further processing
    all_modules = list(latest_modules.values())
    
    # Check if we have all required modules
    if len(all_modules) < 4:
        return HttpResponse("You need to finish all Modules")
    
    # Prepare a dictionary to hold questions for each module
    questions = {
        'english': {'m1': [], 'm2': []},
        'math': {'m1': [], 'm2': []}
    }
    
    # Counters for correct answers and total time spent (per module)
    correct_counts = {'english': {'m1': 0, 'm2': 0}, 'math': {'m1': 0, 'm2': 0}}
    time_spent_totals = {'english': {'m1': 0, 'm2': 0}, 'math': {'m1': 0, 'm2': 0}}
    
    # Loop through each module and process the answers
    for module in all_modules:
        try:
            answers_list = json.loads(module.answers)['answers']
        except Exception:
            answers_list = []
        
        sec = module.section  # should be 'english' or 'math'
        mod = module.module   # should be 'm1' or 'm2'
        if sec not in ['english', 'math'] or mod not in ['m1', 'm2']:
            continue
        
        for answer in answers_list:
            try:
                time_spent = int(answer.get('time_spent', 0))
                time_spent_totals[sec][mod] += time_spent
                
                if sec == 'english':
                    q_obj = English_Question.objects.get(id=int(answer['questionID']))
                    is_correct = (answer['answer'] == q_obj.answer)
                else:  # math
                    q_obj = Math_Question.objects.get(id=int(answer['questionID']))
                    is_correct = (answer['answer'] is not None and check_written(answer['answer'], q_obj.answer))
                
                if is_correct:
                    correct_counts[sec][mod] += 1
                
                questions[sec][mod].append({
                    'id': answer['questionID'],
                    'status': 'correct' if is_correct else 'incorrect',
                    'answer': answer['answer'],
                    'number': q_obj.number,
                    'time_spent': time_spent
                })
            except Exception:
                continue
    
    # Calculate total score using your calculator function
    score = calculator.get_total(
        correct_counts['english']['m1'],
        correct_counts['english']['m2'],
        correct_counts['math']['m1'],
        correct_counts['math']['m2']
    )
    
    # Set up the test review key
    key = 'default'
    testreview, created = TestReview.objects.get_or_create(user=user, test=test_obj)
    if created:
        testreview.update_key()
        # Set review duration based on user group
        if user.groups.filter(name='OFFLINE').exists():
            testreview.duration = timedelta(days=3)  # 3 days for OFFLINE users
        # Admin users and regular users keep default (24 hours)
        # Admin users have unlimited time via is_active() method
    key = testreview.key
    testreview.score = score['total']
    testreview.save()
    
    # Aggregate overall statistics
    total_correct = (
        correct_counts['english']['m1'] +
        correct_counts['english']['m2'] +
        correct_counts['math']['m1'] +
        correct_counts['math']['m2']
    )
    total_time = (
        time_spent_totals['english']['m1'] +
        time_spent_totals['english']['m2'] +
        time_spent_totals['math']['m1'] +
        time_spent_totals['math']['m2']
    )
    
    stats = {
        'total': total_correct,
        'test': test_obj.name,
        'time_spent': total_time,
        'english_time': time_spent_totals['english']['m1'] + time_spent_totals['english']['m2'],
        'math_time': time_spent_totals['math']['m1'] + time_spent_totals['math']['m2'],
    }
    
    # With all 4 modules complete, we mark status['total'] as True
    status = {'total': True}
    
    return render(request, 'test/results.html', {
        "status": status,
        'score': score,
        'stats': stats,
        'key': key,
        'questions': questions,
        'domains': testreview.domains
    })
    

@login_required(login_url='/login/')
def start_Practise(request, pk):
    user_groups = request.user.groups.all()
    test = Test.objects.filter(name=pk, groups__in=user_groups).distinct()
    if is_member(request.user, ['Admin', 'Tester']):
        test = Test.objects.filter(name=pk)

    test_stage = TestStage.objects.filter(user=request.user, test=test[0])
    if test_stage.exists():
        return redirect('test', pk=test[0])

    if test.exists():
        return render(request, 'test/test_modules.html', {'test': test[0]})
    return HttpResponse('Test is Not Found')


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
    except MakeupTest.DoesNotExist:
        return HttpResponse('Makeup Test Not Found or Permission Denied')

    test_stage = TestStage.objects.filter(user=user, makeup_test=makeup_test, test_type='makeup')
    if test_stage.exists():
        return redirect('makeup_test_module', pk=makeup_test.name)

    return render(request, 'test/makeup_test_start.html', {'makeup_test': makeup_test})


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
    except:
        return HttpResponse('Permission Error')
    # Use get_or_create to prevent race conditions and ensure no duplicates
    test_stage, created = TestStage.objects.get_or_create(user=user, test=test, defaults={'stage': 1})

    test, section, module = test_stage.get_models()
    m = TestModule.objects.filter(test=test, section=section, module=module, user=user)
    if m.exists():
        if test_stage.next_stage():
            return redirect('results', test=test)
        return module_test(request, pk=test.pk)

    # Get user's custom time settings for offline users
    custom_time_seconds = None
    if user.groups.filter(name='OFFLINE').exists():
        # Use get_or_create to prevent race conditions
        profile, created = UserProfile.objects.get_or_create(user=user)
        if section == 'english':
            custom_time_seconds = profile.get_english_time_seconds()
        elif section == 'math':
            custom_time_seconds = profile.get_math_time_seconds()

    if section == 'english':
        questions = English_Question.objects.filter(test=test, module=f'module_{module[1]}').order_by('number')
        if questions.exists():
            context = {
                'questions': questions, 
                'module': module, 
                'test': test, 
                'section': section,
                'custom_time_seconds': custom_time_seconds
            }
            return render(request, 'test/test_eng.html', context)
        else:
            return HttpResponse('Questions are not found')

    if section == 'math':
        questions = Math_Question.objects.filter(test=test, module=f'module_{module[1]}').order_by('number')
        if questions.exists():
            context = {
                'questions': questions, 
                'module': module, 
                'test': test, 
                'section': section,
                'custom_time_seconds': custom_time_seconds
            }
            return render(request, 'test/test_math.html', context)
        else:
            return HttpResponse('Questions are not found')

    return HttpResponse("You dont have permission my guy")


def rankings(request, pk):
    results = TestReview.objects.filter(test__name=pk).order_by('-score', 'user')[:50]
    return render(request, 'test/features/rankings.html', {'results': results})


@allowed_users(['Admin'])
def results_by_user(request, test, username):
    questions = {
        'english': {
            'm1': [], 'm2': []
        },
        'math': {
            'm1': [], 'm2': []
        }
    }
    a = 0
    e = 0
    l = 0
    u = 0 
    status = {
        'english': False,
        'math': False,
        'total': False
    }
    test = Test.objects.get(name=test)
    user = User.objects.get(username=username)
    english_modules = TestModule.objects.filter(user=user, test=test, section='english')
    if len(english_modules) == 2:
        status['english'] = True
        eng_m1 = english_modules.filter(module='m1').first()
        eng_m2 = english_modules.filter(module='m2').first()
        for question in json.loads(eng_m1.answers)['answers']:
            try:
                if question['answer'] == English_Question.objects.get(id=question['questionID']).answer:
                    a += 1
                    questions['english']['m1'].append({'id': question['questionID'], 'status': 'correct', 'answer': question['answer'], 'number': English_Question.objects.get(id=question['questionID']).number})
                else:
                    questions['english']['m1'].append({'id': question['questionID'], 'status': 'incorrect', 'answer': question['answer'], 'number': English_Question.objects.get(id=question['questionID']).number})
            except:
                continue
        for question in json.loads(eng_m2.answers)['answers']:
            try:
                if question['answer'] == English_Question.objects.get(id=question['questionID']).answer:
                    e += 1
                    questions['english']['m2'].append({'id': question['questionID'], 'status': 'correct', 'answer': question['answer'], 'number': English_Question.objects.get(id=question['questionID']).number})
                else:
                   questions['english']['m2'].append({'id': question['questionID'], 'status': 'incorrect', 'answer': question['answer'], 'number': English_Question.objects.get(id=question['questionID']).number})
            except:
                continue

    math_modules = TestModule.objects.filter(user=user, test=test, section='math')
    if len(math_modules) == 2:
        status['math'] = True
        math_m1 = math_modules.filter(module='m1').first()
        math_m2 = math_modules.filter(module='m2').first()
        for question in json.loads(math_m1.answers)['answers']:
            try:
                if question['answer'] is None:
                    questions['math']['m1'].append({'id': question['questionID'], 'status': 'incorrect', 'answer': question['answer'], 'number': Math_Question.objects.get(id=question['questionID']).number})
                    continue
                if check_written(question['answer'], Math_Question.objects.get(id=question['questionID']).answer):
                    l += 1 
                    questions["math"]['m1'].append({'id': question['questionID'], 'status': 'correct', 'answer': question['answer'].replace('/', '-'), 'number': Math_Question.objects.get(id=question['questionID']).number})
                else:
                    questions["math"]['m1'].append({'id': question['questionID'], 'status': 'incorrect', 'answer': question['answer'].replace('/', '-'), 'number': Math_Question.objects.get(id=question['questionID']).number})
            except:
                continue
        for question in json.loads(math_m2.answers)['answers']:
            try:
                if question['answer'] is None:
                    questions['math']['m2'].append({'id': question['questionID'], 'status': 'incorrect', 'answer': question['answer'], 'number': Math_Question.objects.get(id=question['questionID']).number})
                    continue
                if check_written(question['answer'], Math_Question.objects.get(id=question['questionID']).answer):
                    u += 1
                    questions["math"]['m2'].append({'id': question['questionID'], 'status': 'correct', 'answer': question['answer'].replace('/', '-'), 'number': Math_Question.objects.get(id=question['questionID']).number})
                else:
                    questions["math"]['m2'].append({'id': question['questionID'], 'status': 'incorrect', 'answer': question['answer'].replace('/', '-'), 'number': Math_Question.objects.get(id=question['questionID']).number})
            except:
                continue

    if status['english'] and status['math']:
        status['total'] = True

    score = calculator.get_total(a, e, l, u)
    key = 'default'

    if is_member(user, ['Both', 'Trial']):
        if status['total']:
            testreview, created = TestReview.objects.get_or_create(user=user, test=test)
            if created:
                testreview.update_key()
                # Set review duration based on user group
                if user.groups.filter(name='OFFLINE').exists():
                    testreview.duration = timedelta(days=3)  # 3 days for OFFLINE users
                # Admin users and regular users keep default (24 hours)
                # Admin users have unlimited time via is_active() method
                testreview.save()
            key = testreview.key
        else:
            return HttpResponse('You need to finish all Modules')
    else:
        if status['english'] or status['math']:
            testreview, created = TestReview.objects.get_or_create(user=user, test=test)
            if created:
                testreview.update_key()
                # Set review duration based on user group
                if user.groups.filter(name='OFFLINE').exists():
                    testreview.duration = timedelta(days=3)  # 3 days for OFFLINE users
                # Admin users and regular users keep default (24 hours)
                # Admin users have unlimited time via is_active() method
                testreview.save()
            key = testreview.key
        else:
            return HttpResponse('You need to finish all Modules')
    testreview.score = score['total']
    testreview.save()

    return render(request, 'test/results.html', {'user': user, "status": status, 'score': score, 'stats': {'total': a + e + l + u, 'test': test}, 'key': key, 'questions': questions })


@login_required(login_url='login')
def certificate(request, test):
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
    a = 0
    e = 0
    l = 0
    u = 0 
    test = Test.objects.get(pk=test)
    user = request.user
    testreview = TestReview.objects.filter(user=user, test=test)
    
    if testreview.exists():
        testreview = testreview[0]
        response = testreview.check_and_update_domains()
        if not testreview.domains:
            print(response)
            return HttpResponse('Domains are not entered to this practise questions')
        if testreview.certificate != '':
            try:
                # Check if it's an R2 path (new format) or local file (old format)
                if testreview.certificate.startswith('certificates/'):
                    # R2 storage - redirect to signed URL
                    from apps.sat.storages import PrivateStorage
                    storage = PrivateStorage()
                    signed_url = storage.url(testreview.certificate)
                    return HttpResponseRedirect(signed_url)
                else:
                    # Legacy local file - serve directly
                    return FileResponse(open(testreview.certificate, 'rb'), content_type='application/pdf')
            except Exception as e:
                print(f"Certificate access error: {e}")
                pass
    else:
        return HttpResponse("Invalid TEST review contact tech@sat800makon.uz")
    
    code = testreview.key
    path = BASE_DIR
    output = str(testreview)

    english_modules = TestModule.objects.filter(user=user, test=test, section='english')
    eng_m1 = english_modules.filter(module='m1').first()
    eng_m2 = english_modules.filter(module='m2').first()
    for question in json.loads(eng_m1.answers)['answers']:
        try:
            db_question = English_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] == db_question.answer:
                a += 1
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue
    for question in json.loads(eng_m2.answers)['answers']:
        try:
            db_question = English_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] == db_question.answer:
                e += 1
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue

    math_modules = TestModule.objects.filter(user=user, test=test, section='math')
    math_m1 = math_modules.filter(module='m1').first()
    math_m2 = math_modules.filter(module='m2').first()
    for question in json.loads(math_m1.answers)['answers']:
        try:
            db_question = Math_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] is None:
                questions['wrongs'][db_question.domain.name] += 1
                continue
            if check_written(question['answer'], Math_Question.objects.get(id=question['questionID']).answer):
                l += 1 
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue
    for question in json.loads(math_m2.answers)['answers']:
        try:
            db_question = Math_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] is None:
                questions['wrongs'][db_question.domain.name] += 1
                continue
            if check_written(question['answer'], Math_Question.objects.get(id=question['questionID']).answer):
                u += 1 
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue

    score = calculator.get_total(a, e, l, u)
        
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
        counts[i] = custom_round((totals[i] - wrongs[i]) / totals[i] * 7)
        

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

    # Certificate is now stored in R2, redirect to signed URL
    from apps.sat.storages import PrivateStorage

    storage = PrivateStorage()
    signed_url = storage.url(testreview.certificate)
    return HttpResponseRedirect(signed_url)


@allowed_users(['Admin'])
def certificate_by_user(request, test, username):
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
    a = 0
    e = 0
    l = 0
    u = 0 
    test = Test.objects.get(pk=test)
    user = User.objects.get(username=username)
    testreview = TestReview.objects.filter(user=user, test=test)
    
    if testreview.exists():
        testreview = testreview[0]
        testreview.check_and_update_domains()
        if not testreview.domains:
            return HttpResponse('Domains are not entered to this practise questions')
        # if testreview.certificate != '':
        #     return FileResponse(open(testreview.certificate, 'rb'), content_type='application/pdf')
    else:
        return HttpResponse("Invalid TEST review contact tech@sat800makon.uz")
    
    code = testreview.key
    path = BASE_DIR
    output = str(testreview)

    english_modules = TestModule.objects.filter(user=user, test=test, section='english')
    eng_m1 = english_modules.filter(module='m1').first()
    eng_m2 = english_modules.filter(module='m2').first()
    for question in json.loads(eng_m1.answers)['answers']:
        try:
            db_question = English_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] == db_question.answer:
                a += 1
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue
    for question in json.loads(eng_m2.answers)['answers']:
        try:
            db_question = English_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] == db_question.answer:
                e += 1
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue

    math_modules = TestModule.objects.filter(user=user, test=test, section='math')
    math_m1 = math_modules.filter(module='m1').first()
    math_m2 = math_modules.filter(module='m2').first()
    for question in json.loads(math_m1.answers)['answers']:
        try:
            db_question = Math_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] is None:
                questions['wrongs'][db_question.domain.name] += 1
                continue
            if check_written(question['answer'], Math_Question.objects.get(id=question['questionID']).answer):
                l += 1 
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue
    for question in json.loads(math_m2.answers)['answers']:
        try:
            db_question = Math_Question.objects.get(id=question['questionID'])
            questions['total'][db_question.domain.name] += 1
            if question['answer'] is None:
                questions['wrongs'][db_question.domain.name] += 1
                continue
            if check_written(question['answer'], Math_Question.objects.get(id=question['questionID']).answer):
                u += 1 
            else:
                questions['wrongs'][db_question.domain.name] += 1
        except:
            continue

    score = calculator.get_total(a, e, l, u)
        
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
        counts[i] = custom_round((totals[i] - wrongs[i]) / totals[i] * 7)

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

    # Certificate is now stored in R2, redirect to signed URL
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
            # Update the TestReview score after section reset
            testreview = TestReview.objects.filter(user=user, test=test).first()
            if testreview:
                testreview.score = 0  # Reset score or recalculate based on remaining section
                testreview.save()
            
            return render(request, 'sat/restart_success.html', {
                'test_name': pk,
                'section': section
            })
        else:
            # Get user group name for display
            user_group = 'OFFLINE' if user.groups.filter(name='OFFLINE').exists() else 'Standard'
            
            return render(request, 'sat/retake_limit_exceeded.html', {
                'test_name': pk,
                'section': section,
                'retakes_used': stage.retake_count,
                'max_retakes': stage.get_max_retakes(),
                'user_group': user_group
            })
    
    return HttpResponse("You do not have permission to restart sections")

@login_required
def menu_page(request):
    return render(request, 'sat/menu_page.html')


@login_required
def vocabulary(request):
    return render(request, 'sat/vocabulary.html')


@login_required
def admissions(request):
    return render(request, 'sat/admissions.html')