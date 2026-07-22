from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import SupportTeacherAvailability, SupportTeacherProfile


class SupportTeacherSelfProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)

    SCORE_FIELDS = ('sat_total_score', 'sat_math_score', 'sat_reading_writing_score')

    class Meta:
        model = SupportTeacherProfile
        fields = [
            'display_name',
            'headline',
            'subjects',
            'bio',
            'education',
            'languages',
            'years_experience',
            'sat_total_score',
            'sat_math_score',
            'sat_reading_writing_score',
            'telegram_username',
            'meeting_link',
            'booking_instructions',
            'min_booking_notice_hours',
            'cancellation_notice_hours',
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'Public teacher name'}),
            'headline': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'Example: SAT Math specialist and strategy coach'}),
            'subjects': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'SAT Math, Reading & Writing, Test Strategy'}),
            'bio': forms.Textarea(attrs={'class': 'support-textarea', 'rows': 5, 'placeholder': 'Describe your teaching approach, strengths, and the students you help best.'}),
            'education': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'University, degree, certification, or credential'}),
            'languages': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'English, Uzbek, Russian'}),
            'years_experience': forms.NumberInput(attrs={'class': 'support-input', 'min': 0, 'max': 50}),
            'sat_total_score': forms.NumberInput(attrs={'class': 'support-input', 'min': 400, 'max': 1600, 'placeholder': '400–1600'}),
            'sat_math_score': forms.NumberInput(attrs={'class': 'support-input', 'min': 200, 'max': 800, 'placeholder': '200–800'}),
            'sat_reading_writing_score': forms.NumberInput(attrs={'class': 'support-input', 'min': 200, 'max': 800, 'placeholder': '200–800'}),
            'telegram_username': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'username without @'}),
            'meeting_link': forms.URLInput(attrs={'class': 'support-input', 'placeholder': 'https://meet.google.com/...'}),
            'booking_instructions': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'What should students prepare before the lesson?'}),
            'min_booking_notice_hours': forms.NumberInput(attrs={'class': 'support-input', 'min': 0, 'max': 168}),
            'cancellation_notice_hours': forms.NumberInput(attrs={'class': 'support-input', 'min': 0, 'max': 168}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user if self.instance and self.instance.pk else None
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
        for name in ('first_name', 'last_name', 'email'):
            self.fields[name].widget.attrs.update({'class': 'support-input'})

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            return email
        qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.user_id:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise ValidationError('This email address is already used by another account.')
        return email

    def clean_telegram_username(self):
        return (self.cleaned_data.get('telegram_username') or '').strip().lstrip('@')

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get('sat_total_score')
        math = cleaned.get('sat_math_score')
        rw = cleaned.get('sat_reading_writing_score')
        if math and rw:
            expected = math + rw
            if total and total != expected:
                self.add_error('sat_total_score', f'Total SAT score must equal Math + Reading & Writing ({expected}).')
            elif not total:
                cleaned['sat_total_score'] = expected
        elif total and math and total < math:
            self.add_error('sat_total_score', 'Total SAT score cannot be lower than the Math score.')
        elif total and rw and total < rw:
            self.add_error('sat_total_score', 'Total SAT score cannot be lower than the Reading & Writing score.')
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        score_changed = False
        if profile.pk:
            old = SupportTeacherProfile.objects.filter(pk=profile.pk).values(*self.SCORE_FIELDS).first() or {}
            score_changed = any(old.get(field) != self.cleaned_data.get(field) for field in self.SCORE_FIELDS)
        if score_changed:
            profile.scores_verified = False

        user = profile.user
        user.first_name = (self.cleaned_data.get('first_name') or '').strip()
        user.last_name = (self.cleaned_data.get('last_name') or '').strip()
        user.email = (self.cleaned_data.get('email') or '').strip().lower()
        if commit:
            user.save(update_fields=['first_name', 'last_name', 'email'])
            profile.save()
        return profile


class SupportTeacherSelfAvailabilityForm(forms.ModelForm):
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
            'day_of_week': forms.Select(attrs={'class': 'support-select'}),
            'start_time': forms.TimeInput(attrs={'class': 'support-input', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'support-input', 'type': 'time'}),
            'slot_duration_minutes': forms.NumberInput(attrs={'class': 'support-input', 'min': 15, 'max': 180, 'step': 15}),
            'buffer_minutes': forms.NumberInput(attrs={'class': 'support-input', 'min': 0, 'max': 60, 'step': 5}),
            'note': forms.TextInput(attrs={'class': 'support-input', 'placeholder': 'Optional note shown with the slot'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'support-checkbox'}),
        }
