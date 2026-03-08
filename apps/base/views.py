# base/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.urls import reverse
from .forms import UserRegistrationForm, EditProfileForm
from datetime import timezone
from .models import EmailVerification
from .decorators import *

def software(request):
    return render(request, 'software.html')

@login_required(login_url='/login/')
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        form = EditProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = EditProfileForm(instance=user)
    return render(request, 'base/edit_profile.html', {'form': form})

@login_required(login_url='/login/')
def home(request):
    return redirect('dashboard')

@unauthenticated_user
def loginUser(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("dashboard")
            else:
                messages.error(request, "Your account is not active. Please check your email for the activation link.")
        else:
            messages.error(request, "Username or password is incorrect.")
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
            # Save the user to the database
            user = form.save()
            user.set_password(form.cleaned_data["password"])
            user.save()

            # Create and save the email verification with a token
            verification = EmailVerification.objects.create(user=user)

            # Generate activation URL
            activation_url = request.build_absolute_uri(reverse('activate', kwargs={'token': str(verification.token)}))

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