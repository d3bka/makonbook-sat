from django import forms
from django.contrib.auth.models import Group, User
from .models import Test, SupportTeacherProfile, SupportTeacherAvailability


class UserFilterForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.all().order_by('name'),
        required=False,
        empty_label="-- All Groups --",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    username = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search username...'})
    )
    status = forms.ChoiceField(
        choices=[('', '-- All --'), ('active', 'Active'), ('inactive', 'Inactive')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class UserGroupEditForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )


class GroupCreateForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'New group name'})
    )


class MockCreateForm(forms.Form):
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mock name (e.g. March Mock 2026)'})
    )
    test = forms.ModelChoiceField(
        queryset=Test.objects.all().order_by('name'),
        empty_label=None,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    user_count = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=10,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    mode = forms.ChoiceField(
        choices=[('direct', 'Direct'), ('secret_code', 'Secret Code')],
        widget=forms.RadioSelect(),
        initial='direct'
    )
    username_prefix = forms.CharField(
        max_length=50,
        initial='user',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. student'})
    )
    password_length = forms.IntegerField(
        min_value=8,
        max_value=20,
        initial=12,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

class GroupAssignedTestsForm(forms.Form):
    tests = forms.ModelMultipleChoiceField(
        queryset=Test.objects.all().order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        group = kwargs.pop('group')
        super().__init__(*args, **kwargs)
        self.group = group
        self.fields['tests'].initial = group.tests.all()

    def save(self):
        current_tests = self.group.tests.all()
        for test in current_tests:
            test.groups.remove(self.group)

        for test in self.cleaned_data['tests']:
            test.groups.add(self.group)


class SupportTeacherProfileForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Choose the platform user who will act as a support teacher.'
    )

    class Meta:
        model = SupportTeacherProfile
        fields = [
            'user',
            'display_name',
            'headline',
            'telegram_username',
            'subjects',
            'bio',
            'education',
            'languages',
            'years_experience',
            'sat_total_score',
            'sat_math_score',
            'sat_reading_writing_score',
            'scores_verified',
            'meeting_link',
            'booking_instructions',
            'min_booking_notice_hours',
            'cancellation_notice_hours',
            'sort_order',
            'is_active',
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Public name shown to students'}),
            'headline': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SAT Math specialist and strategy coach'}),
            'telegram_username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'username without @'}),
            'subjects': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SAT Math, Reading, Writing'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Short public description'}),
            'education': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'University, degree, or certification'}),
            'languages': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'English, Uzbek, Russian'}),
            'years_experience': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 50}),
            'sat_total_score': forms.NumberInput(attrs={'class': 'form-control', 'min': 400, 'max': 1600}),
            'sat_math_score': forms.NumberInput(attrs={'class': 'form-control', 'min': 200, 'max': 800}),
            'sat_reading_writing_score': forms.NumberInput(attrs={'class': 'form-control', 'min': 200, 'max': 800}),
            'scores_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'meeting_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://meet.google.com/...'}),
            'booking_instructions': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Example: Send your question screenshots before the lesson'}),
            'min_booking_notice_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 168}),
            'cancellation_notice_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 168}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_telegram_username(self):
        value = (self.cleaned_data.get('telegram_username') or '').strip().lstrip('@')
        return value


class SupportTeacherAvailabilityForm(forms.ModelForm):
    class Meta:
        model = SupportTeacherAvailability
        fields = [
            'day_of_week',
            'start_time',
            'end_time',
            'slot_duration_minutes',
            'buffer_minutes',
            'note',
            'is_active',
        ]
        widgets = {
            'day_of_week': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'slot_duration_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 15, 'max': 180, 'step': 15}),
            'buffer_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 60, 'step': 5}),
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional note'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
