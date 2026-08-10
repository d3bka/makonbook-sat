import io
import secrets
import string
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Avg
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from .models import Test, TestReview, Mock, SecretCode, SupportTeacherProfile, SupportTeacherAvailability, SupportLessonBooking
from .forms_admin import UserFilterForm, UserGroupEditForm, GroupCreateForm, MockCreateForm, GroupAssignedTestsForm, SupportTeacherProfileForm, SupportTeacherAvailabilityForm


def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)):
            return password


# --- Permission Check ---
def is_admin_user(user):
    return user.is_authenticated and (
        user.groups.filter(name='Admin').exists()
        or user.is_staff
        or user.is_superuser
    )


admin_panel_required = user_passes_test(is_admin_user, login_url='/login/')


# --- Dashboard ---
@login_required
@admin_panel_required
def admin_dashboard(request):
    context = {
        'user_count': User.objects.count(),
        'group_count': Group.objects.count(),
        'test_count': Test.objects.count(),
        'mock_count': Mock.objects.count(),
        'support_teacher_count': SupportTeacherProfile.objects.count(),
        'active_support_teacher_count': SupportTeacherProfile.objects.filter(is_active=True).count(),
        'support_booking_count': SupportLessonBooking.objects.count(),
        'page_title': 'Admin Dashboard',
        'active_page': 'dashboard',
    }
    return render(request, 'sat/admin/dashboard.html', context)


# --- Users ---
@login_required
@admin_panel_required
def admin_users(request):
    form = UserFilterForm(request.GET or None)
    users = User.objects.all().order_by('-date_joined')

    if form.is_valid():
        group = form.cleaned_data.get('group')
        username = form.cleaned_data.get('username')
        status = form.cleaned_data.get('status')

        if group:
            users = users.filter(groups=group)
        if username:
            users = users.filter(username__icontains=username)
        if status == 'active':
            users = users.filter(is_active=True)
        elif status == 'inactive':
            users = users.filter(is_active=False)

    paginator = Paginator(users, 50)
    page = request.GET.get('page')
    users_page = paginator.get_page(page)

    context = {
        'form': form,
        'users': users_page,
        'page_title': 'Users',
        'active_page': 'users',
    }
    return render(request, 'sat/admin/users.html', context)


@login_required
@admin_panel_required
def admin_user_detail(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    groups = target_user.groups.all()
    reviews = TestReview.objects.filter(user=target_user).order_by('-created_at')[:20]

    context = {
        'target_user': target_user,
        'groups': groups,
        'reviews': reviews,
        'page_title': f'User: {target_user.username}',
        'active_page': 'users',
    }
    return render(request, 'sat/admin/user_detail.html', context)


@login_required
@admin_panel_required
def admin_user_edit(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        form = UserGroupEditForm(request.POST)
        if form.is_valid():
            target_user.groups.set(form.cleaned_data['groups'])
            messages.success(request, f"Groups updated for '{target_user.username}'.")
            return redirect('admin_user_detail', user_id=target_user.pk)
    else:
        form = UserGroupEditForm(initial={'groups': target_user.groups.all()})

    context = {
        'target_user': target_user,
        'form': form,
        'page_title': f'Edit: {target_user.username}',
        'active_page': 'users',
    }
    return render(request, 'sat/admin/user_edit.html', context)


@login_required
@admin_panel_required
def admin_user_delete(request, user_id):
    if request.method == 'POST':
        target_user = get_object_or_404(User, pk=user_id)
        username = target_user.username
        target_user.delete()
        messages.success(request, f"User '{username}' deleted.")
    return redirect('admin_users')


@login_required
def admin_user_create(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        group_id = request.POST.get("group")

        if not username or not password:
            messages.error(request, "Username and password are required.")
            return redirect("admin_user_create")

        if User.objects.filter(username=username).exists():
            messages.error(request, "User already exists.")
            return redirect("admin_user_create")

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        if group_id:
            group = Group.objects.get(id=group_id)
            user.groups.add(group)

        messages.success(request, f"User {username} created successfully.")
        return redirect("admin_users")

    groups = Group.objects.all()

    return render(request, "sat/admin/user_create.html", {
        "groups": groups,
        "page_title": "Create User",
        "active_page": "users",
    })

# --- Groups ---
@login_required
@admin_panel_required
def admin_groups(request):
    if request.method == 'POST':
        form = GroupCreateForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            if not Group.objects.filter(name=name).exists():
                Group.objects.create(name=name)
                messages.success(request, f"Group '{name}' created.")
            else:
                messages.error(request, f"Group '{name}' already exists.")
            return redirect('admin_groups')
    else:
        form = GroupCreateForm()

    groups = Group.objects.all().annotate(member_count=Count('user')).order_by('name')

    context = {
        'groups': groups,
        'form': form,
        'page_title': 'Groups',
        'active_page': 'groups',
    }
    return render(request, 'sat/admin/groups.html', context)


@login_required
@admin_panel_required
def admin_group_detail(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    members = group.user_set.all().order_by('username')
    tests = group.tests.all()
    secret_codes = SecretCode.objects.filter(group=group)
    assigned_tests_form = GroupAssignedTestsForm(group=group)

    context = {
        'group': group,
        'members': members,
        'tests': tests,
        'secret_codes': secret_codes,
        'page_title': f'Group: {group.name}',
        'active_page': 'groups',
        'assigned_tests_form': assigned_tests_form,
    }
    return render(request, 'sat/admin/group_detail.html', context)


@login_required
@admin_panel_required
def admin_group_delete(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    users_to_delete = list(group.user_set.all())

    if request.method == "POST":
        confirmation_name = request.POST.get("confirmation_name", "").strip()

        if confirmation_name != group.name:
            messages.error(request, "Group name confirmation does not match.")
            return render(request, "sat/admin/group_delete.html", {
                "group": group,
                "users_count": len(users_to_delete),
            })

        group_name = group.name
        users_count = len(users_to_delete)

        with transaction.atomic():
            for user in users_to_delete:
                user.delete()
            group.delete()

        messages.success(
            request,
            f'Group "{group_name}" and {users_count} users were deleted successfully.'
        )
        return redirect("admin_groups")

    return render(request, "sat/admin/group_delete.html", {
        "group": group,
        "users_count": len(users_to_delete),
    })


@login_required
@admin_panel_required
def admin_group_remove_user(request, group_id, user_id):
    if request.method == 'POST':
        group = get_object_or_404(Group, pk=group_id)
        user = get_object_or_404(User, pk=user_id)
        group.user_set.remove(user)
        messages.success(request, f"Removed '{user.username}' from '{group.name}'.")
    return redirect('admin_group_detail', group_id=group_id)


# --- Tests ---
@login_required
@admin_panel_required
def admin_tests(request):
    tests = Test.objects.all().order_by('name')
    test_data = []
    for test in tests:
        groups = test.groups.all()
        completion_count = TestReview.objects.filter(test=test).count()
        test_data.append({
            'test': test,
            'groups': groups,
            'completion_count': completion_count,
        })

    context = {
        'test_data': test_data,
        'page_title': 'Tests',
        'active_page': 'tests',
    }
    return render(request, 'sat/admin/tests.html', context)


@login_required
@admin_panel_required
def admin_test_detail(request, test_name):
    test = get_object_or_404(Test, pk=test_name)
    groups = test.groups.all()
    completion_count = TestReview.objects.filter(test=test).count()

    context = {
        'test': test,
        'groups': groups,
        'completion_count': completion_count,
        'page_title': f'Test: {test.name}',
        'active_page': 'tests',
    }
    return render(request, 'sat/admin/test_detail.html', context)


# --- Mocks ---
@login_required
@admin_panel_required
def admin_mocks(request):
    mocks = Mock.objects.all().order_by('-created_at')

    context = {
        'mocks': mocks,
        'page_title': 'Mocks',
        'active_page': 'mocks',
    }
    return render(request, 'sat/admin/mocks.html', context)


@login_required
@admin_panel_required
def admin_mock_create(request):
    if request.method == 'POST':
        form = MockCreateForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            test = form.cleaned_data['test']
            user_count = form.cleaned_data['user_count']
            mode = form.cleaned_data['mode']
            prefix = form.cleaned_data['username_prefix']
            pw_length = form.cleaned_data['password_length']

            try:
                with transaction.atomic():
                    # Create group
                    group_name = f"mock_{name.replace(' ', '_')}"
                    group, _ = Group.objects.get_or_create(name=group_name)

                    # Assign test to group
                    test.groups.add(group)

                    # Create users
                    created_users = []
                    for i in range(1, user_count + 1):
                        username = f"{prefix}_{i}"
                        password = generate_password(pw_length)
                        if User.objects.filter(username=username).exists():
                            continue
                        user = User.objects.create_user(username=username, password=password)
                        if mode == 'direct':
                            user.groups.add(group)
                        created_users.append({'username': username, 'password': password})

                    # Build credentials CSV
                    cred_lines = "Username,Password\n"
                    for u in created_users:
                        cred_lines += f"{u['username']},{u['password']}\n"

                    # Create secret code if needed
                    secret_code_obj = None
                    if mode == 'secret_code':
                        secret_code_obj = SecretCode.objects.create(
                            group=group,
                            test=test,
                        )

                    # Create Mock record
                    mock = Mock.objects.create(
                        name=name,
                        test=test,
                        group=group,
                        secret_code=secret_code_obj,
                        mode=mode,
                        user_count=len(created_users),
                        credentials=cred_lines,
                        created_by=request.user,
                    )

                messages.success(request, f"Mock '{name}' created with {len(created_users)} users.")
                return redirect('admin_mock_detail', mock_id=mock.pk)

            except Exception as e:
                messages.error(request, f"Error creating mock: {e}")
                return redirect('admin_mock_create')
    else:
        form = MockCreateForm()

    context = {
        'form': form,
        'page_title': 'Create Mock',
        'active_page': 'mocks',
    }
    return render(request, 'sat/admin/mock_create.html', context)


@login_required
@admin_panel_required
def admin_mock_detail(request, mock_id):
    mock = get_object_or_404(Mock, pk=mock_id)

    context = {
        'mock': mock,
        'page_title': f'Mock: {mock.name}',
        'active_page': 'mocks',
    }
    return render(request, 'sat/admin/mock_detail.html', context)


@login_required
@admin_panel_required
def admin_mock_download(request, mock_id):
    mock = get_object_or_404(Mock, pk=mock_id)
    buffer = io.StringIO(mock.credentials)
    response = HttpResponse(buffer.getvalue(), content_type='text/plain')
    filename = f"{mock.name.replace(' ', '_')}_credentials.txt"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


#--- Group Assigned Tests ---
@login_required
def edit_group_tests(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if request.method == 'POST':
        form = GroupAssignedTestsForm(request.POST, group=group)
        if form.is_valid():
            form.save()
            messages.success(request, f"Assigned tests updated for {group.name}")
            return redirect('admin_group_detail', group_id=group.id)
    else:
        form = GroupAssignedTestsForm(group=group)

    return render(request, 'sat/admin/edit_group_tests.html', {
        'group': group,
        'form': form,
    })

# Mock Deletion
@login_required
def admin_mock_delete(request, mock_id):
    mock = get_object_or_404(Mock, pk=mock_id)
    group = mock.group
    secret_code = mock.secret_code

    if request.method == 'POST':
        confirmation_name = request.POST.get('confirmation_name', '').strip()

        if confirmation_name != mock.name:
            messages.error(request, 'Mock name confirmation does not match.')
            return render(request, 'sat/admin/mock_delete.html', {
                'mock': mock,
                'group': group,
            })

        # Save related users before deleting anything
        users_to_delete = list(group.user_set.all()) if group else []

        mock_name = mock.name
        group_name = group.name if group else 'No group'
        users_count = len(users_to_delete)

        with transaction.atomic():
            # delete secret code if attached
            if secret_code:
                secret_code.delete()

            # delete the mock itself
            mock.delete()

            # delete generated users
            for user in users_to_delete:
                user.delete()

            # delete the group
            if group:
                group.delete()

        messages.success(
            request,
            f'Mock "{mock_name}" was deleted together with group "{group_name}" and {users_count} users.'
        )
        return redirect('admin_mocks')

    return render(request, 'sat/admin/mock_delete.html', {
        'mock': mock,
        'group': group,
    })


# --- Support Teachers ---
@login_required
@admin_panel_required
def admin_support_teachers(request):
    now_value = timezone.now()
    teachers = (
        SupportTeacherProfile.objects.select_related('user')
        .prefetch_related('availabilities')
        .annotate(
            upcoming_count=Count(
                'bookings',
                filter=Q(bookings__status=SupportLessonBooking.STATUS_SCHEDULED, bookings__end_at__gte=now_value),
                distinct=True,
            ),
            admin_avg_rating=Avg('reviews__rating'),
            admin_reviews_count=Count('reviews', distinct=True),
        )
        .order_by('sort_order', 'display_name', 'user__username')
    )
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        teachers = teachers.filter(
            Q(display_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(telegram_username__icontains=query)
            | Q(subjects__icontains=query)
        )

    if status == 'active':
        teachers = teachers.filter(is_active=True)
    elif status == 'inactive':
        teachers = teachers.filter(is_active=False)

    paginator = Paginator(teachers, 30)
    teachers_page = paginator.get_page(request.GET.get('page'))

    return render(request, 'sat/admin/support_teachers.html', {
        'teachers': teachers_page,
        'query': query,
        'status': status,
        'page_title': 'Support Teachers',
        'active_page': 'support_teachers',
    })


@login_required
@admin_panel_required
def admin_support_bookings(request):
    bookings = SupportLessonBooking.objects.select_related(
        'teacher', 'teacher__user', 'student', 'lesson_title', 'lesson_topic', 'session'
    ).order_by('-created_at')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    teacher_id = request.GET.get('teacher', '').strip()
    date_from = parse_date(request.GET.get('date_from', '').strip())
    date_to = parse_date(request.GET.get('date_to', '').strip())

    if query:
        bookings = bookings.filter(
            Q(student__username__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(teacher__display_name__icontains=query)
            | Q(teacher__user__username__icontains=query)
            | Q(student_note__icontains=query)
        )
    if status in dict(SupportLessonBooking.STATUS_CHOICES):
        bookings = bookings.filter(status=status)
    if teacher_id.isdigit():
        bookings = bookings.filter(teacher_id=int(teacher_id))
    if date_from:
        bookings = bookings.filter(start_at__date__gte=date_from)
    if date_to:
        bookings = bookings.filter(start_at__date__lte=date_to)

    summary = SupportLessonBooking.objects.aggregate(
        total=Count('id'),
        requested=Count('id', filter=Q(status=SupportLessonBooking.STATUS_REQUESTED)),
        scheduled=Count('id', filter=Q(status=SupportLessonBooking.STATUS_SCHEDULED)),
        completed=Count('id', filter=Q(status=SupportLessonBooking.STATUS_COMPLETED)),
        cancelled=Count('id', filter=Q(status=SupportLessonBooking.STATUS_CANCELLED)),
        no_show=Count('id', filter=Q(status=SupportLessonBooking.STATUS_NO_SHOW)),
    )
    paginator = Paginator(bookings, 40)
    bookings_page = paginator.get_page(request.GET.get('page'))

    return render(request, 'sat/admin/support_bookings.html', {
        'bookings': bookings_page,
        'teachers': SupportTeacherProfile.objects.select_related('user').order_by('sort_order', 'display_name'),
        'summary': summary,
        'query': query,
        'status': status,
        'teacher_id': teacher_id,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': SupportLessonBooking.STATUS_CHOICES,
        'page_title': 'Support Bookings',
        'active_page': 'support_bookings',
    })


@login_required
@admin_panel_required
def admin_support_teacher_create(request):
    if request.method == 'POST':
        form = SupportTeacherProfileForm(request.POST)
        if form.is_valid():
            teacher = form.save(commit=False)
            teacher.created_by = request.user
            teacher.save()
            support_group, _ = Group.objects.get_or_create(name='Support Teacher')
            teacher.user.groups.add(support_group)
            messages.success(request, f"Support teacher '{teacher.name}' created.")
            return redirect('admin_support_teacher_edit', teacher_id=teacher.id)
    else:
        form = SupportTeacherProfileForm()

    return render(request, 'sat/admin/support_teacher_form.html', {
        'form': form,
        'teacher': None,
        'availability_form': None,
        'availabilities': [],
        'recent_bookings': [],
        'page_title': 'Create Support Teacher',
        'active_page': 'support_teachers',
    })


@login_required
@admin_panel_required
def admin_support_teacher_edit(request, teacher_id):
    teacher = get_object_or_404(SupportTeacherProfile.objects.select_related('user'), id=teacher_id)

    if request.method == 'POST':
        form = SupportTeacherProfileForm(request.POST, instance=teacher)
        if form.is_valid():
            teacher = form.save()
            support_group, _ = Group.objects.get_or_create(name='Support Teacher')
            teacher.user.groups.add(support_group)
            messages.success(request, f"Support teacher '{teacher.name}' updated.")
            return redirect('admin_support_teacher_edit', teacher_id=teacher.id)
    else:
        form = SupportTeacherProfileForm(instance=teacher)

    availability_form = SupportTeacherAvailabilityForm(initial={'is_active': True})
    availabilities = teacher.availabilities.all().order_by('day_of_week', 'start_time')
    recent_bookings = SupportLessonBooking.objects.filter(teacher=teacher).select_related('student', 'lesson_title', 'lesson_topic', 'session').order_by('-created_at')[:20]

    return render(request, 'sat/admin/support_teacher_form.html', {
        'form': form,
        'teacher': teacher,
        'availability_form': availability_form,
        'availabilities': availabilities,
        'recent_bookings': recent_bookings,
        'page_title': f'Edit Support Teacher: {teacher.name}',
        'active_page': 'support_teachers',
    })


@login_required
@admin_panel_required
@transaction.atomic
def admin_support_teacher_toggle(request, teacher_id):
    if request.method != 'POST':
        return redirect('admin_support_teachers')

    teacher = get_object_or_404(SupportTeacherProfile, id=teacher_id)
    teacher.is_active = not teacher.is_active
    teacher.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, f"Support teacher '{teacher.name}' is now {'active' if teacher.is_active else 'inactive'}.")
    return redirect('admin_support_teachers')


@login_required
@admin_panel_required
def admin_support_teacher_availability_add(request, teacher_id):
    teacher = get_object_or_404(SupportTeacherProfile, id=teacher_id)
    if request.method != 'POST':
        return redirect('admin_support_teacher_edit', teacher_id=teacher.id)

    form = SupportTeacherAvailabilityForm(request.POST)
    if form.is_valid():
        availability = form.save(commit=False)
        availability.teacher = teacher
        try:
            availability.full_clean()
            availability.save()
            messages.success(request, "Availability slot added.")
        except Exception as exc:
            messages.error(request, f"Could not save availability: {exc}")
    else:
        messages.error(request, "Availability form has invalid values.")

    return redirect('admin_support_teacher_edit', teacher_id=teacher.id)


@login_required
@admin_panel_required
def admin_support_teacher_availability_delete(request, teacher_id, availability_id):
    teacher = get_object_or_404(SupportTeacherProfile, id=teacher_id)
    if request.method != 'POST':
        return redirect('admin_support_teacher_edit', teacher_id=teacher.id)

    availability = get_object_or_404(SupportTeacherAvailability, id=availability_id, teacher=teacher)
    availability.delete()
    messages.success(request, "Availability slot deleted.")
    return redirect('admin_support_teacher_edit', teacher_id=teacher.id)
