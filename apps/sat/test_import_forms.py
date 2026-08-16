from django import forms

from .models import Test, TestImportJob, TestImportQuestion
from .test_import_service import validate_import_question


class TestImportUploadForm(forms.ModelForm):
    class Meta:
        model = TestImportJob
        fields = ["name", "requested_test_type", "source_pdf", "answer_pdf", "required_approvals"]
        widgets = {"required_approvals": forms.NumberInput(attrs={"min": 1, "max": 5})}

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Test name is required.")
        if Test.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("A published test with this name already exists.")
        return name

    def clean_required_approvals(self):
        value = int(self.cleaned_data.get("required_approvals") or 2)
        if value < 1 or value > 5:
            raise forms.ValidationError("Required approvals must be between 1 and 5.")
        return value

    def clean_source_pdf(self):
        f = self.cleaned_data.get("source_pdf")
        if not f:
            return f
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Upload a PDF file.")
        if f.size > 49 * 1024 * 1024:
            raise forms.ValidationError("PDF must be smaller than 49 MB.")
        return f

    def clean_answer_pdf(self):
        f = self.cleaned_data.get("answer_pdf")
        if f and not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Answer file must be a PDF.")
        if f and f.size > 24 * 1024 * 1024:
            raise forms.ValidationError("Answer/reference PDF must be smaller than 24 MB.")
        return f


class TestImportQuestionForm(forms.ModelForm):
    class Meta:
        model = TestImportQuestion
        fields = [
            "number", "passage", "question", "a", "b", "c", "d", "answer", "explanation",
            "image", "image_a", "image_b", "image_c", "image_d",
            "response_type", "written", "graph", "choice_graph", "source_page",
        ]
        widgets = {
            "passage": forms.Textarea(attrs={"rows": 6}),
            "question": forms.Textarea(attrs={"rows": 4}),
            "a": forms.Textarea(attrs={"rows": 2}), "b": forms.Textarea(attrs={"rows": 2}),
            "c": forms.Textarea(attrs={"rows": 2}), "d": forms.Textarea(attrs={"rows": 2}),
            "explanation": forms.Textarea(attrs={"rows": 5}),
        }

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit:
            validate_import_question(obj)
        return obj
