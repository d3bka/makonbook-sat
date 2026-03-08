from django.forms import ModelForm
from django.contrib.auth.models import User


from django import forms
from .models import UserProfile

class UserRegistrationForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        help_text="Enter a valid email address for verification."
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        help_text="Enter a password (minimum 8 characters)."
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirm Password",
        help_text="Re-enter your password for confirmation."
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email address is already in use.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user

class UserBatchCreationForm(forms.Form):
    prefix = forms.CharField(label='Prefix', max_length=50)
    number_of_users = forms.IntegerField(label='Number of Users', min_value=1, max_value=100)

class EditProfileForm(forms.ModelForm):
    english_time_minutes = forms.IntegerField(
        min_value=10, 
        max_value=120, 
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'English section time (minutes)'
        }),
        help_text="Time limit for English section (10-120 minutes)"
    )
    math_time_minutes = forms.IntegerField(
        min_value=10, 
        max_value=120, 
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Math section time (minutes)'
        }),
        help_text="Time limit for Math section (10-120 minutes)"
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        
        # Only show time fields for offline users
        if self.user and self.user.groups.filter(name='OFFLINE').exists():
            # Get or create user profile
            profile, created = UserProfile.objects.get_or_create(user=self.user)
            self.fields['english_time_minutes'].initial = profile.english_time_minutes
            self.fields['math_time_minutes'].initial = profile.math_time_minutes
        else:
            # Remove time fields for non-offline users
            del self.fields['english_time_minutes']
            del self.fields['math_time_minutes']

    def save(self, commit=True):
        user = super().save(commit=commit)
        
        # Save profile data only for offline users
        if user.groups.filter(name='OFFLINE').exists():
            profile, created = UserProfile.objects.get_or_create(user=user)
            if 'english_time_minutes' in self.cleaned_data:
                profile.english_time_minutes = self.cleaned_data['english_time_minutes']
            if 'math_time_minutes' in self.cleaned_data:
                profile.math_time_minutes = self.cleaned_data['math_time_minutes']
            profile.save()
        
        return user


class UserForm(ModelForm):
    class Meta:
        model = User
        fields = ['first_name','last_name','email','username','password']

    def save(self, commit=True):
        user = super(UserForm, self).save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user