# base/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.core.mail import EmailMultiAlternatives
from django.utils.crypto import get_random_string
from django.urls import reverse
from .forms import UserRegistrationForm, EditProfileForm, ForgotPasswordRequestForm, PasswordResetCodeForm
from datetime import timedelta
from django.utils import timezone
from .models import EmailVerification, PasswordResetCode
from .registration_rate_limit import check_registration_rate_limit
from .decorators import *
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
import unicodedata

def software(request):
    return render(request, 'software.html')

@login_required(login_url='/login/')
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        form = EditProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('sat_menu')
    else:
        form = EditProfileForm(instance=user)
    return render(request, 'base/edit_profile.html', {'form': form})

PROFILE_NAME_APOSTROPHES = {"'", "’", "‘", "ʻ", "ʼ", "`", "´"}
PROFILE_NAME_SEPARATORS = PROFILE_NAME_APOSTROPHES | {"-", " "}


def _normalize_profile_name(value):
    """Normalize harmless whitespace/Unicode differences without changing casing."""
    value = unicodedata.normalize("NFC", (value or "").strip())
    return " ".join(value.split())


def _validate_profile_name(value, label):
    """Return a human-readable validation error, or None when the name is valid."""
    if not value:
        return f"Enter your {label.lower()}."

    if len(value) < 2 or len(value) > 50:
        return f"{label} must be between 2 and 50 characters."

    letter_count = 0
    for char in value:
        category = unicodedata.category(char)
        if category.startswith("L"):
            letter_count += 1
            continue
        if category.startswith("M"):
            # Combining marks are safe after NFC normalization and allow names
            # written with less-common diacritics.
            continue
        if char in PROFILE_NAME_SEPARATORS:
            continue
        return f"{label} can contain only letters, spaces, hyphens, and apostrophes."

    if letter_count < 2:
        return f"{label} must contain at least 2 letters."

    first_category = unicodedata.category(value[0])
    last_category = unicodedata.category(value[-1])
    if not first_category.startswith("L") or not (last_category.startswith("L") or last_category.startswith("M")):
        return f"{label} must start and end with a letter."

    punctuation = PROFILE_NAME_APOSTROPHES | {"-"}
    for previous, current in zip(value, value[1:]):
        if previous in punctuation and current in punctuation:
            return f"{label} has repeated punctuation."

    return None


@login_required(login_url='/login/')
@require_POST
def complete_profile_name(request):
    """Save the required display name from the post-login profile prompt."""
    from django.http import JsonResponse

    first_name = _normalize_profile_name(request.POST.get('first_name'))
    last_name = _normalize_profile_name(request.POST.get('last_name'))

    errors = {}
    first_error = _validate_profile_name(first_name, 'First name')
    last_error = _validate_profile_name(last_name, 'Last name')
    if first_error:
        errors['first_name'] = first_error
    if last_error:
        errors['last_name'] = last_error

    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400)

    user = request.user
    user.first_name = first_name
    user.last_name = last_name
    user.save(update_fields=['first_name', 'last_name'])

    return JsonResponse({
        'ok': True,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name() or user.get_username(),
    })


def home(request):
    """Public landing page for guests; dashboard entry for logged-in users."""
    if request.user.is_authenticated:
        return redirect('sat_menu')
    return render(request, 'landing/home.html')

@unauthenticated_user
def loginUser(request):
    if request.method == "POST":
        credential = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""

        username_for_auth = credential
        if "@" in credential:
            User = get_user_model()
            matched_user = User.objects.filter(email__iexact=credential).order_by("id").first()
            if matched_user:
                username_for_auth = matched_user.get_username()

        user = authenticate(request, username=username_for_auth, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("sat_menu")
            messages.error(request, "Your account is not active. Please contact support.")
        else:
            messages.error(request, "Username/email or password is incorrect.")
    context = {}
    return render(request, 'base/login.html', context)

@login_required(login_url="login")
def logoutUser(request):
    logout(request)
    return redirect("/login")

@unauthenticated_user
def register(request):
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        rate = check_registration_rate_limit(
            request,
            email=request.POST.get("email", ""),
            username=request.POST.get("username", ""),
        )
        if not rate.allowed:
            messages.error(
                request,
                "Too many registration attempts. Please wait a little before trying again.",
            )
            response = render(request, 'base/register.html', {'form': form}, status=429)
            response['Retry-After'] = str(rate.retry_after)
            return response

        if form.is_valid():
            # Save the user to the database. The form hashes and normalizes the password/email.
            user = form.save()

            # # Create and save the email verification with a token
            # verification = EmailVerification.objects.create(user=user)

            # # Generate activation URL
            # activation_url = request.build_absolute_uri(reverse('activate', kwargs={'token': str(verification.token)}))

            # Email verification temporarily disabled.
            user.is_active = True
            user.save(update_fields=["is_active"])
            
            EmailVerification.objects.update_or_create(
                user=user,
                defaults={
                    "is_verified": True,
                    "expires_at": timezone.now() + timedelta(days=3650),
                }
            )

            # # Send the activation email
            # subject = 'Activate Your MakonBook Account'
            # message = f'Hi {user.username},\n\nThank you for registering! Please click the link below to activate your account:\n\n{activation_url}\n\nThis link will expire in 24 hours.\n\nThanks,\nThe MakonBook Team'
            # from_email = 'tech@sat800makon.uz'
            # recipient_list = [user.email]
            # try:
            #     send_mail(subject, message, from_email, recipient_list, fail_silently=False)
            # except Exception as e:
            #     messages.error(request, f"Failed to send activation email: {str(e)}. Please try again later.")
            #     return redirect('register')

            # # Redirect to login page with success message
            # messages.success(request, f"Activation email sent to your email from tech@sat800makon.uz.")
            return redirect('login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.capitalize()}: {error}")
    else:
        form = UserRegistrationForm()
    return render(request, 'base/register.html', {'form': form})



@unauthenticated_user
def forgot_password(request):
    if request.method == "POST":
        form = ForgotPasswordRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            request.session["password_reset_email"] = email

            User = get_user_model()
            user = User.objects.filter(email__iexact=email, is_active=True).order_by("id").first()

            if user:
                code = get_random_string(6, allowed_chars="0123456789")
                PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)
                reset_code = PasswordResetCode.objects.create(
                    user=user,
                    email=email,
                    code_hash=make_password(code),
                    expires_at=timezone.now() + timedelta(minutes=10),
                )

                subject = "Reset your MakonBook password"
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", "")
                support_email = getattr(settings, "EMAIL_HOST_USER", "") or "support@makonbook.uz"
                reset_url = request.build_absolute_uri(reverse("password_reset_confirm"))
                display_name = (user.get_full_name() or user.get_username()).strip()
                email_context = {
                    "display_name": display_name,
                    "code": code,
                    "expires_minutes": 10,
                    "reset_url": reset_url,
                    "support_email": support_email,
                    "current_year": timezone.localdate().year,
                }
                text_body = render_to_string("emails/password_reset_code.txt", email_context)
                html_body = render_to_string("emails/password_reset_code.html", email_context)

                try:
                    email_message = EmailMultiAlternatives(
                        subject=subject,
                        body=text_body,
                        from_email=from_email,
                        to=[user.email],
                        reply_to=[support_email] if support_email else None,
                    )
                    email_message.attach_alternative(html_body, "text/html")
                    email_message.send(fail_silently=False)
                except Exception as exc:
                    reset_code.delete()
                    if settings.DEBUG:
                        messages.error(request, f"Email sending failed: {exc}")
                    else:
                        messages.error(request, "Email sending failed. Please contact support.")
                    return redirect("forgot_password")

            messages.success(request, "If this email exists, a confirmation code has been sent.")
            return redirect("password_reset_confirm")
    else:
        form = ForgotPasswordRequestForm()

    return render(request, "base/forgot_password.html", {"form": form})


@unauthenticated_user
def password_reset_confirm(request):
    initial_email = request.session.get("password_reset_email", "")

    if request.method == "POST":
        form = PasswordResetCodeForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            code = form.cleaned_data["code"].strip()
            new_password = form.cleaned_data["new_password"]

            User = get_user_model()
            user = User.objects.filter(email__iexact=email, is_active=True).order_by("id").first()
            generic_error = "Invalid or expired confirmation code."

            reset_code = None
            if user:
                reset_code = PasswordResetCode.objects.filter(
                    user=user,
                    email__iexact=email,
                    is_used=False,
                ).order_by("-created_at").first()

            if not user or not reset_code or reset_code.is_expired:
                messages.error(request, generic_error)
                return render(request, "base/password_reset_confirm.html", {"form": form})

            if reset_code.attempts >= 5:
                reset_code.is_used = True
                reset_code.save(update_fields=["is_used"])
                messages.error(request, "Too many wrong attempts. Request a new code.")
                return redirect("forgot_password")

            if not check_password(code, reset_code.code_hash):
                reset_code.attempts += 1
                reset_code.save(update_fields=["attempts"])
                messages.error(request, generic_error)
                return render(request, "base/password_reset_confirm.html", {"form": form})

            try:
                validate_password(new_password, user=user)
            except ValidationError as exc:
                for error in exc.messages:
                    messages.error(request, error)
                return render(request, "base/password_reset_confirm.html", {"form": form})

            user.set_password(new_password)
            user.save(update_fields=["password"])

            reset_code.is_used = True
            reset_code.save(update_fields=["is_used"])
            PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)
            request.session.pop("password_reset_email", None)

            messages.success(request, "Password changed successfully. You can now sign in with your new password.")
            return redirect("login")
    else:
        form = PasswordResetCodeForm(initial={"email": initial_email})

    return render(request, "base/password_reset_confirm.html", {"form": form})


@unauthenticated_user
def activate(request, token):
    try:
        verification = EmailVerification.objects.get(token=token, is_verified=False, expires_at__gte=timezone.now())
        user = verification.user
        user.is_active = True
        user.save()
        verification.is_verified = True
        verification.save()
        messages.success(request, f"Account activated! You can now log in with {user.username}.")
    except EmailVerification.DoesNotExist:
        messages.error(request, "Invalid or expired activation link.")
    return redirect('login')

@require_POST
def submit_general_issue_report(request):
    from django.http import JsonResponse
    from django.utils import timezone
    from .models import GeneralIssueReport

    # Lightweight per-session rate limit: at most 5 submissions in one hour.
    now_ts = int(timezone.now().timestamp())
    recent = [int(ts) for ts in request.session.get("issue_report_times", []) if now_ts - int(ts) < 3600]
    if len(recent) >= 5:
        return JsonResponse({"ok": False, "error": "Too many reports. Try again later."}, status=429)

    # Honeypot field for basic bot filtering.
    if (request.POST.get("website") or "").strip():
        return JsonResponse({"ok": True})

    message_text = (request.POST.get("message") or "").strip()
    if len(message_text) < 10:
        return JsonResponse({"ok": False, "error": "Describe the problem in at least 10 characters."}, status=400)

    category = (request.POST.get("category") or "technical").strip()
    valid_categories = {value for value, _ in GeneralIssueReport.CATEGORY_CHOICES}
    if category not in valid_categories:
        category = "other"

    context_payload = {}
    raw_context = (request.POST.get("context_json") or "")[:8000].strip()
    if raw_context:
        try:
            import json
            parsed_context = json.loads(raw_context)
            if isinstance(parsed_context, dict):
                # Keep only a small, non-secret snapshot useful for reproducing the issue.
                context_payload = {}
                for key, value in list(parsed_context.items())[:30]:
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        context_payload[str(key)[:80]] = value[:2000] if isinstance(value, str) else value
        except (TypeError, ValueError, json.JSONDecodeError):
            context_payload = {}

    report = GeneralIssueReport.objects.create(
        reporter=request.user if request.user.is_authenticated else None,
        reporter_name=(request.POST.get("reporter_name") or "")[:160].strip(),
        reporter_email=(request.POST.get("reporter_email") or "")[:254].strip(),
        category=category,
        message=message_text[:4000],
        page_url=(request.POST.get("page_url") or request.META.get("HTTP_REFERER") or "")[:1000],
        page_title=(request.POST.get("page_title") or "")[:300],
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:1000],
        context_data=context_payload,
    )
    recent.append(now_ts)
    request.session["issue_report_times"] = recent
    return JsonResponse({"ok": True, "report_id": report.pk})
