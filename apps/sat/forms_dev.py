from django import forms
from django.contrib.auth.models import Group
from .models import Test, MakeupTest, QuestionDomain, QuestionType, English_Question, Math_Question

class QuestionSearchForm(forms.Form):
    query = forms.CharField(required=False, label="Search Text", widget=forms.TextInput(attrs={'placeholder': 'Enter keywords...'}))
    test = forms.ModelChoiceField(queryset=Test.objects.all(), required=False, empty_label="-- All Tests --")
    domain = forms.ModelChoiceField(queryset=QuestionDomain.objects.all(), required=False, empty_label="-- All Domains --")
    question_type = forms.ModelChoiceField(queryset=QuestionType.objects.all(), required=False, label="Type", empty_label="-- All Types --")
    section = forms.ChoiceField(choices=[('', '-- All Sections --'), ('english', 'English'), ('math', 'Math')], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['test'].widget.attrs.update({'class': 'form-control'})
        self.fields['domain'].widget.attrs.update({'class': 'form-control'})
        self.fields['question_type'].widget.attrs.update({'class': 'form-control'})
        self.fields['section'].widget.attrs.update({'class': 'form-control'})
        self.fields['query'].widget.attrs.update({'class': 'form-control'})

class GroupCreateForm(forms.Form):
    name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'New group name'}))

class BulkUserCreateForm(forms.Form):
    group = forms.ModelChoiceField(queryset=Group.objects.all(), required=True, empty_label=None, widget=forms.Select(attrs={'class': 'form-control'}))
    username_prefix = forms.CharField(max_length=50, required=True, initial='user', help_text="Prefix for generated usernames (e.g., 'student')", widget=forms.TextInput(attrs={'class': 'form-control'}))
    count = forms.IntegerField(min_value=1, max_value=100, required=True, initial=10, help_text="Number of users to create (max 100)", widget=forms.NumberInput(attrs={'class': 'form-control'}))
    password_length = forms.IntegerField(min_value=8, max_value=20, initial=12, label="Password Length", widget=forms.NumberInput(attrs={'class': 'form-control'}))

class AssignTestForm(forms.Form):
    group = forms.ModelChoiceField(queryset=Group.objects.all(), required=True, empty_label=None, widget=forms.Select(attrs={'class': 'form-control'}))
    test = forms.ModelChoiceField(queryset=Test.objects.all(), required=False, label="Assign Regular Test", empty_label="-- No Regular Test --", widget=forms.Select(attrs={'class': 'form-control'}))
    makeup_test = forms.ModelChoiceField(queryset=MakeupTest.objects.all(), required=False, label="Assign Makeup Test", empty_label="-- No Makeup Test --", widget=forms.Select(attrs={'class': 'form-control'}))
    create_secret_code = forms.BooleanField(required=False, initial=False, label="Generate Secret Code for Group/Test?")

    def clean(self):
        cleaned_data = super().clean()
        test = cleaned_data.get("test")
        makeup_test = cleaned_data.get("makeup_test")
        create_secret_code = cleaned_data.get("create_secret_code")

        if not test and not makeup_test and not create_secret_code:
             raise forms.ValidationError("You must select a test to assign OR choose to create a secret code for the group.")
             
        if test and makeup_test:
            raise forms.ValidationError("Assign either a regular test OR a makeup test, not both.")

        if create_secret_code and not test and not makeup_test:
            # Allow creating a secret code just for the group
            pass
        elif create_secret_code and not test and not makeup_test:
             raise forms.ValidationError("Secret code creation requires assigning either a Regular Test or a Makeup Test.")

        return cleaned_data 

class TestStatsForm(forms.Form):
    test = forms.ModelChoiceField(
        queryset=Test.objects.all().order_by('name'), 
        required=True, 
        empty_label=None, 
        label="Select Test for Statistics",
        widget=forms.Select(attrs={'class': 'form-control'})
    ) 