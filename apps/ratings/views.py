from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.sat.models import Classroom, ClassroomMembership

from .engine import build_board, student_rating
from .forms import RatingAssessmentForm
from .models import RatingAssessment, RatingConfig, RatingProfile


def _is_teacher_for(user, classroom):
    return bool(user.is_authenticated and (user.pk == classroom.teacher_id or user.is_staff or user.is_superuser))


def rating_home(request):
    config = RatingConfig.get_solo()
    board = build_board()
    if request.user.is_authenticated and not request.user.is_staff and not request.user.is_superuser:
        entry = student_rating(request.user)
        history = RatingAssessment.objects.filter(student=request.user).select_related("classroom", "teacher")[:100]
        return render(request, "ratings/student_dashboard.html", {
            "entry": entry,
            "history": history,
            "board": board,
            "config": config,
            "profile": RatingProfile.objects.get_or_create(user=request.user)[0],
        })
    return render(request, "ratings/public_board.html", {"board": board, "config": config})


def public_student(request, student_id):
    config = RatingConfig.get_solo()
    if not config.public_board_enabled:
        raise PermissionDenied("The public leaderboard is disabled.")
    entry = next((row for row in build_board() if row.student_id == student_id), None)
    if not entry:
        raise PermissionDenied("This student is not visible on the public leaderboard.")
    return render(request, "ratings/public_student.html", {"entry": entry})


def parent_lookup(request):
    profile = None
    entry = None
    history = []
    if request.method == "POST":
        now_ts = int(timezone.now().timestamp())
        attempts = [
            int(ts) for ts in request.session.get("rating_parent_lookup_times", [])
            if now_ts - int(ts) < 3600
        ]
        if len(attempts) >= 10:
            messages.error(request, "Too many code attempts. Try again later.")
            return render(request, "ratings/parent_lookup.html", {"profile": None, "entry": None, "history": []}, status=429)

        code = (request.POST.get("code") or "").strip().upper()[:16]
        attempts.append(now_ts)
        request.session["rating_parent_lookup_times"] = attempts
        profile = RatingProfile.objects.select_related("user").filter(parent_access_code=code).first()
        if not profile:
            messages.error(request, "Code not found. Check the code shown in the student's My Rating page.")
        else:
            entry = student_rating(profile.user)
            history = RatingAssessment.objects.filter(student=profile.user).select_related("classroom", "teacher")[:50]
    return render(request, "ratings/parent_lookup.html", {"profile": profile, "entry": entry, "history": history})


@login_required
def teacher_classroom_ratings(request, classroom_id):
    classroom = get_object_or_404(Classroom, pk=classroom_id)
    if not _is_teacher_for(request.user, classroom):
        raise PermissionDenied
    memberships = ClassroomMembership.objects.filter(classroom=classroom, role="student", status="approved").select_related("user").order_by("user__first_name", "user__last_name", "user__username")
    recent = RatingAssessment.objects.filter(classroom=classroom, teacher=request.user).select_related("student")[:30]
    return render(request, "ratings/teacher_classroom.html", {"classroom": classroom, "memberships": memberships, "recent": recent, "config": RatingConfig.get_solo()})


@login_required
def assess_student(request, classroom_id, student_id):
    classroom = get_object_or_404(Classroom, pk=classroom_id)
    if not _is_teacher_for(request.user, classroom):
        raise PermissionDenied
    student = get_object_or_404(User, pk=student_id)
    if not ClassroomMembership.objects.filter(classroom=classroom, user=student, role="student", status="approved").exists():
        raise PermissionDenied("Student is not an approved classroom member.")
    if request.method == "POST":
        form = RatingAssessmentForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.classroom = classroom
            assessment.student = student
            assessment.teacher = request.user
            assessment.full_clean()
            assessment.save()
            messages.success(request, f"Rating saved for {student.get_full_name() or student.username}.")
            next_id = request.POST.get("next_student_id")
            if next_id:
                return redirect("rating_assess_student", classroom_id=classroom.id, student_id=next_id)
            return redirect("rating_teacher_classroom", classroom_id=classroom.id)
    else:
        form = RatingAssessmentForm()
    student_ids = list(ClassroomMembership.objects.filter(classroom=classroom, role="student", status="approved").order_by("user__first_name", "user__last_name", "user__username").values_list("user_id", flat=True))
    next_student_id = None
    if student.pk in student_ids:
        index = student_ids.index(student.pk)
        if index + 1 < len(student_ids):
            next_student_id = student_ids[index + 1]
    return render(request, "ratings/assess_student.html", {"classroom": classroom, "student_obj": student, "form": form, "next_student_id": next_student_id})


@login_required
@require_POST
def edit_assessment(request, assessment_id):
    assessment = get_object_or_404(RatingAssessment, pk=assessment_id)
    if assessment.teacher_id != request.user.pk and not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied
    config = RatingConfig.get_solo()
    if timezone.now() - assessment.created_at > timedelta(days=config.teacher_edit_window_days) and not request.user.is_staff:
        raise PermissionDenied("Teacher edit window has expired.")
    form = RatingAssessmentForm(request.POST, instance=assessment)
    if form.is_valid():
        form.save()
        messages.success(request, "Assessment updated.")
    else:
        messages.error(request, "Assessment was not updated. Check all scores are from 0 to 10.")
    return redirect("rating_teacher_classroom", classroom_id=assessment.classroom_id)
