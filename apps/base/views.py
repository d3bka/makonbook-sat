# base/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.urls import reverse
from .forms import UserRegistrationForm, EditProfileForm, ForgotPasswordRequestForm, PasswordResetCodeForm
from datetime import timedelta
from django.utils import timezone
from .models import EmailVerification, PasswordResetCode
from .decorators import *
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

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

                subject = "Your MakonBook password reset code"
                message = (
                    f"Hi {user.username},\n\n"
                    f"Your password reset code is: {code}\n\n"
                    "This code expires in 10 minutes. "
                    "If you did not request a password reset, ignore this email.\n\n"
                    "MakonBook Team"
                )
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", "")

                try:
                    send_mail(subject, message, from_email, [user.email], fail_silently=False)
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