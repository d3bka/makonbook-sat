from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.sat.roles import is_teacher as has_teacher_access
from apps.sat.models import Classroom, ClassroomMembership

from .engine import build_board, student_rating
from .forms import RatingAssessmentForm
from .models import RatingAssessment, RatingConfig, RatingProfile


PARENT_LANGUAGE_CHOICES = ("en", "ru", "uz")

PARENT_TRANSLATIONS = {
    "en": {
        "page_title": "Parent Rating Access",
        "open_menu": "Open menu",
        "main_navigation": "Main navigation",
        "home": "Home",
        "student_rating": "Student Rating",
        "parent_access": "Parent access",
        "leaderboard": "Leaderboard",
        "landing_page": "Landing page",
        "back_to_makonbook": "Back to MakonBook",
        "parent_title": "Parent access",
        "parent_intro": "Enter the private code shown on the student's My Rating page. Search by full name stays disabled on purpose for privacy.",
        "public_leaderboard": "Public leaderboard",
        "student_access_code": "Student access code",
        "code_placeholder": "Enter access code",
        "open_rating": "Open rating",
        "rank": "Rank",
        "rating": "Rating",
        "assessments": "Assessments",
        "classrooms": "Classrooms",
        "date": "Date",
        "classroom": "Classroom",
        "homework": "Homework",
        "progress": "Progress",
        "activity": "Activity",
        "attendance": "Attendance",
        "behavior": "Behavior",
        "mean": "Mean",
        "no_history": "No rating history is available yet.",
        "footer_text": "Digital SAT practice platform with tests, analytics, classrooms, and student rating.",
        "back_to_top": "Back to top",
        "language": "Language",
        "report_issue": "Report issue",
        "report_problem": "Report a problem",
        "close": "Close",
        "report_description": "Describe what happened and what you expected. This is one general platform report, not an automatic request to change an answer key.",
        "category": "Category",
        "technical_problem": "Technical problem",
        "content_problem": "Question or content problem",
        "account_problem": "Account or access problem",
        "rating_problem": "Rating problem",
        "suggestion": "Suggestion",
        "other": "Other",
        "name_optional": "Name (optional)",
        "email_optional": "Email (optional)",
        "comment": "Comment",
        "comment_placeholder": "Example: I could not open my child's rating page after entering the code...",
        "send_report": "Send report",
        "sending": "Sending...",
        "report_sent": "Report sent. Thank you.",
        "report_failed": "Could not send report.",
        "too_many_attempts": "Too many code attempts. Try again later.",
        "code_not_found": "Code not found. Check the code shown in the student's My Rating page.",
    },
    "ru": {
        "page_title": "Рейтинг ученика — доступ для родителей",
        "open_menu": "Открыть меню",
        "main_navigation": "Главная навигация",
        "home": "Главная",
        "student_rating": "Рейтинг учеников",
        "parent_access": "Для родителей",
        "leaderboard": "Рейтинг",
        "landing_page": "Главная страница",
        "back_to_makonbook": "Вернуться в MakonBook",
        "parent_title": "Доступ для родителей",
        "parent_intro": "Введите личный код, который указан на странице «Мой рейтинг» у ученика. Поиск по полному имени специально отключён для защиты персональных данных.",
        "public_leaderboard": "Общий рейтинг",
        "student_access_code": "Код доступа ученика",
        "code_placeholder": "Введите код доступа",
        "open_rating": "Открыть рейтинг",
        "rank": "Место",
        "rating": "Рейтинг",
        "assessments": "Оценивания",
        "classrooms": "Классы",
        "date": "Дата",
        "classroom": "Класс",
        "homework": "Домашняя работа",
        "progress": "Прогресс",
        "activity": "Активность",
        "attendance": "Посещаемость",
        "behavior": "Поведение",
        "mean": "Среднее",
        "no_history": "Истории оценивания пока нет.",
        "footer_text": "Платформа подготовки к Digital SAT: тесты, аналитика, классы и рейтинг учеников.",
        "back_to_top": "Наверх",
        "language": "Язык",
        "report_issue": "Сообщить о проблеме",
        "report_problem": "Сообщить о проблеме",
        "close": "Закрыть",
        "report_description": "Опишите, что произошло и какой результат вы ожидали. Это общее сообщение о проблеме платформы.",
        "category": "Категория",
        "technical_problem": "Техническая проблема",
        "content_problem": "Проблема с вопросом или содержанием",
        "account_problem": "Проблема с аккаунтом или доступом",
        "rating_problem": "Проблема с рейтингом",
        "suggestion": "Предложение",
        "other": "Другое",
        "name_optional": "Имя (необязательно)",
        "email_optional": "Email (необязательно)",
        "comment": "Комментарий",
        "comment_placeholder": "Например: после ввода кода я не смог открыть рейтинг ребёнка...",
        "send_report": "Отправить",
        "sending": "Отправка...",
        "report_sent": "Сообщение отправлено. Спасибо.",
        "report_failed": "Не удалось отправить сообщение.",
        "too_many_attempts": "Слишком много попыток ввода кода. Попробуйте позже.",
        "code_not_found": "Код не найден. Проверьте код на странице «Мой рейтинг» у ученика.",
    },
    "uz": {
        "page_title": "O‘quvchi reytingi — ota-onalar uchun kirish",
        "open_menu": "Menyuni ochish",
        "main_navigation": "Asosiy navigatsiya",
        "home": "Bosh sahifa",
        "student_rating": "O‘quvchilar reytingi",
        "parent_access": "Ota-onalar uchun",
        "leaderboard": "Reyting",
        "landing_page": "Bosh sahifa",
        "back_to_makonbook": "MakonBook’ga qaytish",
        "parent_title": "Ota-onalar uchun kirish",
        "parent_intro": "O‘quvchining «Mening reytingim» sahifasida ko‘rsatilgan shaxsiy kodni kiriting. Maxfiylikni himoya qilish uchun to‘liq ism bo‘yicha qidiruv ataylab o‘chirilgan.",
        "public_leaderboard": "Umumiy reyting",
        "student_access_code": "O‘quvchining kirish kodi",
        "code_placeholder": "Kirish kodini kiriting",
        "open_rating": "Reytingni ochish",
        "rank": "O‘rin",
        "rating": "Reyting",
        "assessments": "Baholashlar",
        "classrooms": "Sinflar",
        "date": "Sana",
        "classroom": "Sinf",
        "homework": "Uy vazifasi",
        "progress": "O‘sish",
        "activity": "Faollik",
        "attendance": "Davomat",
        "behavior": "Xulq-atvor",
        "mean": "O‘rtacha",
        "no_history": "Hozircha baholash tarixi mavjud emas.",
        "footer_text": "Digital SAT tayyorgarlik platformasi: testlar, tahlil, sinflar va o‘quvchilar reytingi.",
        "back_to_top": "Yuqoriga",
        "language": "Til",
        "report_issue": "Muammo haqida xabar berish",
        "report_problem": "Muammo haqida xabar berish",
        "close": "Yopish",
        "report_description": "Nima sodir bo‘lganini va qanday natija kutganingizni yozing. Bu platformadagi umumiy muammo haqida xabar.",
        "category": "Toifa",
        "technical_problem": "Texnik muammo",
        "content_problem": "Savol yoki kontent bilan bog‘liq muammo",
        "account_problem": "Hisob yoki kirish bilan bog‘liq muammo",
        "rating_problem": "Reyting bilan bog‘liq muammo",
        "suggestion": "Taklif",
        "other": "Boshqa",
        "name_optional": "Ism (ixtiyoriy)",
        "email_optional": "Email (ixtiyoriy)",
        "comment": "Izoh",
        "comment_placeholder": "Masalan: kodni kiritganimdan keyin farzandimning reytingini ocha olmadim...",
        "send_report": "Yuborish",
        "sending": "Yuborilmoqda...",
        "report_sent": "Xabar yuborildi. Rahmat.",
        "report_failed": "Xabarni yuborib bo‘lmadi.",
        "too_many_attempts": "Kod kiritish urinishlari juda ko‘p. Keyinroq qayta urinib ko‘ring.",
        "code_not_found": "Kod topilmadi. O‘quvchining «Mening reytingim» sahifasidagi kodni tekshiring.",
    },
}


def _parent_language(request):
    requested = (request.GET.get("lang") or request.POST.get("lang") or "").strip().lower()
    if requested in PARENT_LANGUAGE_CHOICES:
        request.session["rating_parent_language"] = requested
        return requested

    saved = (request.session.get("rating_parent_language") or "").strip().lower()
    if saved in PARENT_LANGUAGE_CHOICES:
        return saved

    browser_language = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").lower()
    for token in browser_language.split(","):
        code = token.split(";", 1)[0].strip().split("-", 1)[0]
        if code in PARENT_LANGUAGE_CHOICES:
            request.session["rating_parent_language"] = code
            return code

    request.session["rating_parent_language"] = "en"
    return "en"


def _parent_context(request, **extra):
    language = _parent_language(request)
    context = {
        "parent_lang": language,
        "parent_t": PARENT_TRANSLATIONS[language],
        "parent_languages": (
            ("en", "English"),
            ("ru", "Русский"),
            ("uz", "O‘zbekcha"),
        ),
        "issue_report_t": PARENT_TRANSLATIONS[language],
    }
    context.update(extra)
    return context


def _is_teacher_for(user, classroom):
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return bool(has_teacher_access(user) and user.pk == classroom.teacher_id)


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
    language = _parent_language(request)
    translations = PARENT_TRANSLATIONS[language]
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
            messages.error(request, translations["too_many_attempts"])
            return render(
                request,
                "ratings/parent_lookup.html",
                _parent_context(request, profile=None, entry=None, history=[]),
                status=429,
            )

        code = (request.POST.get("code") or "").strip().upper()[:16]
        attempts.append(now_ts)
        request.session["rating_parent_lookup_times"] = attempts
        profile = RatingProfile.objects.select_related("user").filter(parent_access_code=code).first()
        if not profile:
            messages.error(request, translations["code_not_found"])
        else:
            entry = student_rating(profile.user)
            history = RatingAssessment.objects.filter(student=profile.user).select_related("classroom", "teacher")[:50]
    return render(
        request,
        "ratings/parent_lookup.html",
        _parent_context(request, profile=profile, entry=entry, history=history),
    )


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
    assessment = get_object_or_404(RatingAssessment.objects.select_related("classroom"), pk=assessment_id)
    if not _is_teacher_for(request.user, assessment.classroom):
        raise PermissionDenied
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
