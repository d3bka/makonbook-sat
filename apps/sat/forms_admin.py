from django import forms
from django.contrib.auth.models import Group
from .models import Test


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