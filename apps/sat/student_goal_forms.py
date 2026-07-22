from datetime import date

from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import DreamUniversity, StudentGoalProfile


# Official College Board weekend SAT administrations currently published for
# the 2026–27 testing year. Keep this list explicit so students can select a
# real administration instead of entering arbitrary dates.
OFFICIAL_SAT_DATES = (
    date(2026, 8, 22),
    date(2026, 9, 12),
    date(2026, 10, 3),
    date(2026, 11, 7),
    date(2026, 12, 5),
    date(2027, 3, 6),
    date(2027, 5, 1),
    date(2027, 6, 5),
)


class StudentGoalProfileForm(forms.ModelForm):
    """Student-owned SAT goal form with catalogue-controlled choices."""

    UNIVERSITY_PREFIX = 'university:'
    OTHER_VALUE = 'other'

    university_choice = forms.ChoiceField(
        label='Dream university',
        required=True,
        widget=forms.Select(attrs={
            'class': 'sg-input',
            'data-goal-university-select': '1',
        }),
    )
    exam_date = forms.TypedChoiceField(
        label='SAT exam date',
        required=True,
        coerce=date.fromisoformat,
        empty_value=None,
        widget=forms.Select(attrs={
            'class': 'sg-input',
            'data-official-sat-date-select': '1',
        }),
        help_text='Choose one of the nearest official College Board SAT dates.',
    )

    class Meta:
        model = StudentGoalProfile
        fields = [
            'custom_university_name',
            'custom_university_country',
            'custom_average_sat_score',
            'target_sat_score',
            'exam_date',
            'daily_study_minutes_goal',
            'weekly_study_days_goal',
        ]
        widgets = {
            'custom_university_name': forms.TextInput(attrs={
                'class': 'sg-input',
                'placeholder': 'Example: Purdue University',
                'autocomplete': 'organization',
            }),
            'custom_university_country': forms.TextInput(attrs={
                'class': 'sg-input',
                'placeholder': 'Example: United States',
                'autocomplete': 'country-name',
            }),
            'custom_average_sat_score': forms.NumberInput(attrs={
                'class': 'sg-input',
                'min': 400,
                'max': 1600,
                'step': 10,
                'placeholder': 'Example: 1450',
                'inputmode': 'numeric',
            }),
            'target_sat_score': forms.NumberInput(attrs={
                'class': 'sg-input',
                'min': 400,
                'max': 1600,
                'step': 10,
                'placeholder': 'Example: 1450',
                'inputmode': 'numeric',
            }),
            'daily_study_minutes_goal': forms.NumberInput(attrs={
                'class': 'sg-input',
                'min': 15,
                'max': 360,
                'step': 5,
            }),
            'weekly_study_days_goal': forms.NumberInput(attrs={
                'class': 'sg-input',
                'min': 1,
                'max': 7,
                'step': 1,
            }),
        }
        labels = {
            'custom_university_name': 'University name',
            'custom_university_country': 'Country',
            'custom_average_sat_score': 'Average SAT score',
            'target_sat_score': 'Your target SAT score',
            'daily_study_minutes_goal': 'Daily study goal (minutes)',
            'weekly_study_days_goal': 'Study days per week',
        }
        help_texts = {
            'custom_average_sat_score': 'Enter this only when you choose Others.',
            'target_sat_score': 'Enter your own personal SAT target.',
            'daily_study_minutes_goal': 'Choose a pace you can repeat consistently.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        university_filter = Q(is_active=True)
        if self.instance and self.instance.dream_university_id:
            university_filter |= Q(pk=self.instance.dream_university_id)
        universities = list(
            DreamUniversity.objects.filter(university_filter)
            .distinct()
            .order_by('sort_order', 'name')
        )
        self._universities_by_value = {
            f'{self.UNIVERSITY_PREFIX}{university.pk}': university
            for university in universities
        }
        self.fields['university_choice'].choices = [
            ('', 'Choose a university'),
            *[
                (
                    value,
                    f'#{university.qs_rank} · {university.name}'
                    if university.qs_rank else university.name,
                )
                for value, university in self._universities_by_value.items()
            ],
            (self.OTHER_VALUE, 'Others — university not listed'),
        ]

        initial_choice = ''
        if self.instance and self.instance.pk:
            if self.instance.dream_university_id:
                initial_choice = f'{self.UNIVERSITY_PREFIX}{self.instance.dream_university_id}'
            elif self.instance.custom_university_name:
                initial_choice = self.OTHER_VALUE
        self.fields['university_choice'].initial = initial_choice

        today = timezone.localdate()
        available_dates = [item for item in OFFICIAL_SAT_DATES if item >= today]
        current_date = self.instance.exam_date if self.instance and self.instance.exam_date else None
        if current_date and current_date >= today and current_date not in available_dates:
            available_dates.insert(0, current_date)

        date_choices = [('', 'Choose an official SAT date')]
        for sat_date in available_dates:
            days_away = (sat_date - today).days
            proximity = 'today' if days_away == 0 else f'{days_away} days away'
            label = f'{sat_date.strftime("%B %d, %Y")} — {proximity}'
            date_choices.append((sat_date.isoformat(), label))
        self.fields['exam_date'].choices = date_choices

        for field in self.fields.values():
            field.required = False
        self.fields['university_choice'].required = True
        self.fields['target_sat_score'].required = True
        self.fields['exam_date'].required = True
        self.fields['daily_study_minutes_goal'].required = True
        self.fields['weekly_study_days_goal'].required = True

    def clean_university_choice(self):
        choice = (self.cleaned_data.get('university_choice') or '').strip()
        if choice == self.OTHER_VALUE:
            return choice
        if choice not in self._universities_by_value:
            raise forms.ValidationError('Choose a university or select Others.')
        return choice

    def clean(self):
        cleaned = super().clean()
        choice = cleaned.get('university_choice')
        is_other = choice == self.OTHER_VALUE
        selected = self._universities_by_value.get(choice)
        custom_name = (cleaned.get('custom_university_name') or '').strip()
        custom_country = (cleaned.get('custom_university_country') or '').strip()
        custom_average = cleaned.get('custom_average_sat_score')
        target_score = cleaned.get('target_sat_score')
        exam_date = cleaned.get('exam_date')

        if is_other:
            if not custom_name:
                self.add_error('custom_university_name', 'Enter the university name.')
            if not custom_country:
                self.add_error('custom_university_country', 'Enter the country.')
            if not custom_average:
                self.add_error('custom_average_sat_score', 'Enter the average SAT score.')

        reference_score = custom_average if is_other else (
            selected.average_sat_score if selected else None
        )
        if reference_score and target_score and target_score < reference_score:
            self.add_error(
                'target_sat_score',
                f'Your target should be at least the university reference score ({reference_score}).',
            )

        if exam_date and exam_date < timezone.localdate():
            self.add_error('exam_date', 'Exam date cannot be in the past.')
        if exam_date and exam_date not in OFFICIAL_SAT_DATES and exam_date != getattr(self.instance, 'exam_date', None):
            self.add_error('exam_date', 'Choose one of the official SAT dates from the list.')

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        choice = self.cleaned_data['university_choice']

        if choice == self.OTHER_VALUE:
            instance.dream_university = None
            instance.custom_university_name = (
                self.cleaned_data.get('custom_university_name') or ''
            ).strip()
            instance.custom_university_country = (
                self.cleaned_data.get('custom_university_country') or ''
            ).strip()
        else:
            instance.dream_university = self._universities_by_value[choice]
            instance.custom_university_name = ''
            instance.custom_university_country = ''
            instance.custom_average_sat_score = None

        if commit:
            instance.full_clean()
            instance.save()
        return instance
