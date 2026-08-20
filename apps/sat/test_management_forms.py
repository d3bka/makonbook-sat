from django import forms
from django.contrib.auth.models import Group

from .forms import EnglishQuestionForm, MathQuestionForm
from .models import English_Question, Math_Question, Test


class ManagedTestForm(forms.Form):
    name = forms.CharField(max_length=400, label="Test name")
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        label="Restricted groups",
        help_text="Leave empty for the existing public/no-group behavior. Select groups only when this test should be tied to those groups.",
    )
    is_available = forms.BooleanField(
        required=False,
        label="Open for MakonBook users",
        help_text=(
            "Turn this off to block Students, Teachers, Support Teachers and all Classroom attempts across MakonBook. "
            "Guest Mode stays available. Manager/Admin/Tester QA access remains available, and existing progress/results are preserved."
        ),
    )
    icon = forms.ImageField(required=False, label="Test icon")
    remove_icon = forms.BooleanField(required=False, label="Remove current icon")

    def __init__(self, *args, test: Test, **kwargs):
        self.test = test
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.update({
                "name": test.name,
                "groups": list(test.groups.values_list("pk", flat=True)),
                "is_available": test.is_available,
            })

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Test name is required.")
        if Test.objects.filter(name__iexact=name).exclude(pk=self.test.pk).exists():
            raise forms.ValidationError("A test with this name already exists.")
        return name


class ManagedEnglishQuestionForm(EnglishQuestionForm):
    class Meta(EnglishQuestionForm.Meta):
        model = English_Question
        fields = [
            "module", "number", "domain", "type", "passage", "question",
            "a", "b", "c", "d", "graph", "image", "response_type",
            "answer", "accepted_answers", "answer_patterns", "explained",
        ]


class ManagedMathQuestionForm(MathQuestionForm):
    class Meta(MathQuestionForm.Meta):
        model = Math_Question
        fields = [
            "module", "number", "domain", "type", "passage", "question",
            "a", "b", "c", "d", "graph", "image", "choice_graph",
            "image_a", "image_b", "image_c", "image_d", "written",
            "answer", "explained", "img_explain",
        ]
