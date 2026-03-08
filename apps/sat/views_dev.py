# Views specifically for users in the 'dev' group
import secrets
import string
import io
import statistics
from datetime import timedelta
from django.utils import timezone
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, FileResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.db.models import Q # For complex lookups
from django.contrib import messages
from django.db import transaction
from .models import English_Question, Math_Question, Test, MakeupTest, QuestionDomain, SecretCode, QuestionType, TestReview, TestModule
from .forms_dev import QuestionSearchForm, GroupCreateForm, BulkUserCreateForm, AssignTestForm, TestStatsForm
from .views import check_written # Import check_written helper
import traceback # Import traceback module

# --- Permission Check --- 
def is_dev_user(user):
    """Check if the user is in the 'dev' group."""
    # Ensure user is authenticated before checking groups
    return user.is_authenticated and user.groups.filter(name='dev').exists()

# Decorator for dev views
dev_required = user_passes_test(is_dev_user, login_url='/login/')

# --- Helper Functions ---
def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + string.punctuation
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        # Basic complexity check (optional but recommended)
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in string.punctuation for c in password)):
            return password

# --- Dev Views --- 

@login_required
@dev_required
def dev_dashboard(request):
    """Dashboard for the dev mode."""
    context = {
        'page_title': 'Developer Dashboard'
    }
    return render(request, 'sat/dev/dev_dashboard.html', context)

@login_required
@dev_required
def search_questions(request):
    """Search and filter English and Math questions."""
    english_results = English_Question.objects.all()
    math_results = Math_Question.objects.all()
    form = QuestionSearchForm(request.GET or None)

    if form.is_valid():
        query = form.cleaned_data.get('query')
        test = form.cleaned_data.get('test')
        domain = form.cleaned_data.get('domain')
        question_type = form.cleaned_data.get('question_type')
        section = form.cleaned_data.get('section')

        # --- Filtering Logic ---
        # Text Query (searches passage and question text)
        if query:
            english_results = english_results.filter(Q(question__icontains=query) | Q(passage__icontains=query))
            math_results = math_results.filter(Q(question__icontains=query) | Q(passage__icontains=query))

        # Test Filter
        if test:
            english_results = english_results.filter(test=test)
            math_results = math_results.filter(test=test)
            
        # Domain Filter
        if domain:
            english_results = english_results.filter(domain=domain)
            math_results = math_results.filter(domain=domain)
            
        # Type Filter
        if question_type:
            english_results = english_results.filter(type=question_type)
            math_results = math_results.filter(type=question_type)

        # Section Filter (only show results for the selected section if specified)
        if section == 'english':
            math_results = Math_Question.objects.none() # Exclude math
        elif section == 'math':
            english_results = English_Question.objects.none() # Exclude english
            
    # Order results for consistency
    english_results = english_results.order_by('test__name', 'module', 'number')
    math_results = math_results.order_by('test__name', 'module', 'number')

    context = {
        'form': form,
        'english_questions': english_results[:100], # Limit results for performance
        'math_questions': math_results[:100],
        'english_count': english_results.count(),
        'math_count': math_results.count(),
        'page_title': 'Search Questions',
    }
    return render(request, 'sat/dev/search_questions.html', context)

@login_required
@dev_required
def manage_groups(request):
    """View to list groups and handle creation."""
    if request.method == 'POST':
        form = GroupCreateForm(request.POST)
        if form.is_valid():
            group_name = form.cleaned_data['name']
            if not Group.objects.filter(name=group_name).exists():
                Group.objects.create(name=group_name)
                messages.success(request, f"Group '{group_name}' created successfully.")
            else:
                messages.error(request, f"Group '{group_name}' already exists.")
            return redirect('dev_manage_groups') # Redirect to refresh list
    else:
        form = GroupCreateForm()
        
    groups = Group.objects.all().order_by('name')
    context = {
        'groups': groups,
        'form': form,
        'page_title': 'Manage Groups'
    }
    return render(request, 'sat/dev/manage_groups.html', context)

@login_required
@dev_required
def create_bulk_users(request):
    """Create multiple users, add them to a group, and provide credentials."""
    if request.method == 'POST':
        form = BulkUserCreateForm(request.POST)
        if form.is_valid():
            group = form.cleaned_data['group']
            prefix = form.cleaned_data['username_prefix']
            count = form.cleaned_data['count']
            pw_length = form.cleaned_data['password_length']
            
            created_users = []
            errors = []
            
            try:
                with transaction.atomic(): # Ensure all users are created or none are
                    for i in range(1, count + 1):
                        username = f"{prefix}_{group.name}_{i}"
                        password = generate_password(pw_length)
                        
                        if User.objects.filter(username=username).exists():
                            errors.append(f"Username '{username}' already exists. Skipped.")
                            continue
                            
                        user = User.objects.create_user(username=username, password=password)
                        user.groups.add(group)
                        created_users.append({'username': username, 'password': password})
                        
            except Exception as e:
                messages.error(request, f"An error occurred during bulk user creation: {e}")
                return redirect('dev_create_bulk_users')

            if errors:
                for error in errors:
                    messages.warning(request, error)

            if created_users:
                # Generate TXT file content
                file_content = "Username,Password\n"
                for user_data in created_users:
                    file_content += f"{user_data['username']},{user_data['password']}\n"
                
                # Create file response
                buffer = io.StringIO(file_content)
                response = HttpResponse(buffer.getvalue(), content_type='text/plain')
                filename = f"{group.name}_users_{prefix}.txt"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                messages.success(request, f"Successfully created {len(created_users)} users and added to group '{group.name}'. Download the credentials file.")
                return response
            else:
                 messages.info(request, "No users were created.")
                 return redirect('dev_create_bulk_users')

    else:
        form = BulkUserCreateForm()
        
    context = {
        'form': form,
        'page_title': 'Create Bulk Users'
    }
    return render(request, 'sat/dev/create_bulk_users.html', context)

@login_required
@dev_required
def assign_test(request):
    """Assign a test to a group and optionally create a secret code."""
    if request.method == 'POST':
        form = AssignTestForm(request.POST)
        if form.is_valid():
            group = form.cleaned_data['group']
            test = form.cleaned_data.get('test')
            makeup_test = form.cleaned_data.get('makeup_test')
            create_code = form.cleaned_data.get('create_secret_code')
            
            assigned_test_name = "None"
            
            # Assign tests to group
            if test:
                test.groups.add(group)
                assigned_test_name = test.name
                messages.success(request, f"Regular Test '{test.name}' assigned to group '{group.name}'.")
            if makeup_test:
                makeup_test.groups.add(group)
                assigned_test_name = makeup_test.name
                messages.success(request, f"Makeup Test '{makeup_test.name}' assigned to group '{group.name}'.")
            
            # Create secret code if requested
            if create_code:
                secret_code = SecretCode.objects.create(
                    group=group,
                    test=test, 
                    makeup_test=makeup_test
                )
                messages.success(request, f"Secret Code '{secret_code.code}' created for group '{group.name}' (linked to test: {assigned_test_name}).")
                
            return redirect('dev_assign_test') # Redirect after successful assignment
            
    else:
        form = AssignTestForm()

    context = {
        'form': form,
        'page_title': 'Assign Test / Create Code'
    }
    return render(request, 'sat/dev/assign_test.html', context)

@login_required
@dev_required
def test_statistics(request):
    form = TestStatsForm()
    report_data = None

    if request.method == 'POST':
        form = TestStatsForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid form submission. Please check your input.")
            return render(request, 'sat/dev/test_statistics.html', {'form': form})
        
        selected_test = form.cleaned_data['test']
        
        try: # Start try block here
            reviews = TestReview.objects.filter(test=selected_test, score__isnull=False).order_by('-score')
            student_count = reviews.count()
            
            if student_count > 0:
                scores = [r.score for r in reviews if r.score is not None]
                overall_stats = {
                    'student_count': student_count,
                    'average_score': statistics.mean(scores) if scores else 0,
                    'median_score': statistics.median(scores) if scores else 0,
                    'highest_score': max(scores) if scores else 0,
                    'lowest_score': min(scores) if scores else 0,
                }
                top_performers = reviews[:10]
                
                question_correct = {}
                question_attempts = {}
                question_time = {}
                question_info = {}
                malformed_module_data_count = 0
                malformed_answer_data_count = 0
                
                completed_user_ids = reviews.values_list('user_id', flat=True)
                modules = TestModule.objects.filter(test=selected_test, user_id__in=completed_user_ids)
                
                english_qs = {q.id: q for q in English_Question.objects.filter(test=selected_test)}
                math_qs = {q.id: q for q in Math_Question.objects.filter(test=selected_test)}

                for module in modules:
                    try:
                        if not module.answers:
                            malformed_module_data_count += 1
                            continue
                        module_data = json.loads(module.answers)
                        if not isinstance(module_data, dict) or 'answers' not in module_data or not isinstance(module_data['answers'], list):
                            malformed_module_data_count += 1
                            continue
                        answers = module_data['answers']
                    except json.JSONDecodeError:
                        malformed_module_data_count += 1
                        continue
                        
                    for answer_data in answers:
                        try:
                            if not isinstance(answer_data, dict) or 'questionID' not in answer_data:
                                malformed_answer_data_count += 1
                                continue
                            
                            q_id = int(answer_data['questionID'])
                            time_spent = int(answer_data.get('time_spent', 0))
                            user_answer = answer_data.get('answer')
                            
                            question_attempts[q_id] = question_attempts.get(q_id, 0) + 1
                            question_time[q_id] = question_time.get(q_id, 0) + time_spent
                            is_correct = False
                            q_obj = None
                            
                            if module.section == 'english' and q_id in english_qs:
                                q_obj = english_qs[q_id]
                                is_correct = (user_answer == q_obj.answer)
                                if q_id not in question_info:
                                    question_info[q_id] = {'text': q_obj.question[:100]+'... ' if q_obj.question else 'N/A', 'section': 'Eng', 'number': q_obj.number, 'module': q_obj.module }
                            elif module.section == 'math' and q_id in math_qs:
                                q_obj = math_qs[q_id]
                                is_correct = (user_answer is not None and check_written(user_answer, q_obj.answer))
                                if q_id not in question_info:
                                    question_info[q_id] = {'text': q_obj.question[:100]+'... ' if q_obj.question else 'N/A', 'section': 'Math', 'number': q_obj.number, 'module': q_obj.module }
                            
                            if is_correct:
                                question_correct[q_id] = question_correct.get(q_id, 0) + 1
                                
                        except (ValueError, TypeError, KeyError):
                            malformed_answer_data_count += 1
                            continue 
                
                if malformed_module_data_count > 0:
                    messages.warning(request, f"Skipped {malformed_module_data_count} modules due to invalid answer data format.")
                if malformed_answer_data_count > 0:
                    messages.warning(request, f"Skipped {malformed_answer_data_count} individual answers due to invalid data format.")
                
                # --- Calculate and Sort Question Stats --- 
                question_stats = []
                for q_id, attempts in question_attempts.items():
                    if attempts > 0 and q_id in question_info:
                        correct = question_correct.get(q_id, 0)
                        total_time = question_time.get(q_id, 0)
                        question_stats.append({
                            'id': q_id,
                            'info': question_info[q_id],
                            'percentage_correct': (correct / attempts) * 100 if attempts > 0 else 0,
                            'average_time': (total_time / attempts) if attempts > 0 else 0,
                            'attempts': attempts
                        })
                
                hardest_questions = sorted([q for q in question_stats if q['attempts'] > 0], key=lambda x: x['percentage_correct'])[:5]
                easiest_questions = sorted([q for q in question_stats if q['attempts'] > 0], key=lambda x: x['percentage_correct'], reverse=True)[:5]
                longest_time_questions = sorted([q for q in question_stats if q['attempts'] > 0], key=lambda x: x['average_time'], reverse=True)[:5]
                shortest_time_questions = sorted([q for q in question_stats if q['attempts'] > 0], key=lambda x: x['average_time'])[:5]

                # --- Time Interval Analysis --- 
                time_interval_stats = {}
                first_completion_time = reviews.last().created_at if reviews.exists() else timezone.now()
                intervals = {
                    'first_24_hours': first_completion_time + timedelta(days=1),
                    'first_7_days': first_completion_time + timedelta(days=7),
                    'overall': None # Add overall placeholder
                }
                
                for interval_key, end_time in intervals.items():
                    if interval_key == 'overall':
                         # Handle overall stats separately
                         time_interval_stats[interval_key] = {
                            'display_name': 'Overall', # Added display name
                            'count': student_count,
                            'average_score': overall_stats['average_score'],
                            'median_score': overall_stats['median_score'],
                         }
                         continue
                         
                    interval_reviews = reviews.filter(created_at__lte=end_time)
                    interval_scores = [r.score for r in interval_reviews if r.score is not None]
                    display_name = interval_key.replace("_", " ").title() # Create display name
                    time_interval_stats[interval_key] = {
                        'display_name': display_name, # Added display name
                        'count': interval_reviews.count(),
                        'average_score': statistics.mean(interval_scores) if interval_scores else 0,
                        'median_score': statistics.median(interval_scores) if interval_scores else 0,
                    }
                # Remove the now redundant overall calculation from here if it was duplicated

                # --- Set report_data only if successful --- 
                report_data = {
                    'test': selected_test,
                    'overall': overall_stats,
                    'top_performers': top_performers,
                    'questions': {
                        'hardest': hardest_questions,
                        'easiest': easiest_questions,
                        'longest': longest_time_questions,
                        'shortest': shortest_time_questions,
                    },
                    'time_intervals': time_interval_stats
                }
            else:
                messages.warning(request, f"No completed results found for test '{selected_test.name}'.")
                report_data = None # Ensure no report is rendered if no students
                
        except Exception as e:
            # Catch any unexpected error during report generation
            error_type = type(e).__name__
            error_message = str(e)
            messages.error(request, f"Error generating statistics report: {error_type} - {error_message}. Check server logs for details.")
            print("--- ERROR in test_statistics view ---")
            traceback.print_exc() # Print full traceback to console/log
            print("-------------------------------------")
            report_data = None # Ensure no partial report is shown

    context = {
        'form': form,
        'report_data': report_data,
        'page_title': 'Test Statistics Report'
    }
    return render(request, 'sat/dev/test_statistics.html', context)

# More views will be added here... 