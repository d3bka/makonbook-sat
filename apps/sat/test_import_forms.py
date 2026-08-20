from django import forms

from .models import Test, TestImportJob, TestImportQuestion
from .test_import_service import validate_import_question


class TestImportUploadForm(forms.ModelForm):
    class Meta:
        model = TestImportJob
        fields = ["name", "english_pdf", "math_pdf", "required_approvals"]
        widgets = {"required_approvals": forms.NumberInput(attrs={"min": 1, "max": 5})}
        labels = {
            "english_pdf": "EBRW structured PDF",
            "math_pdf": "Math structured PDF",
        }
        help_texts = {
            "english_pdf": "Optional. Upload a MakonBook Structured PDF v2 Reading & Writing file (v1 remains accepted for legacy imports).",
            "math_pdf": "Optional. Upload a MakonBook Structured PDF v2 Math file (v1 remains accepted for legacy imports).",
        }

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

    @staticmethod
    def _clean_pdf(f, label):
        if not f:
            return f
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError(f"{label} must be a PDF file.")
        if f.size > 49 * 1024 * 1024:
            raise forms.ValidationError(f"{label} must be smaller than 49 MB.")
        return f

    def clean_english_pdf(self):
        return self._clean_pdf(self.cleaned_data.get("english_pdf"), "EBRW file")

    def clean_math_pdf(self):
        return self._clean_pdf(self.cleaned_data.get("math_pdf"), "Math file")

    def clean(self):
        cleaned = super().clean()
        if (
            not cleaned.get("english_pdf")
            and not cleaned.get("math_pdf")
            and "english_pdf" not in self.errors
            and "math_pdf" not in self.errors
        ):
            raise forms.ValidationError("Upload at least one structured PDF: EBRW, Math, or both.")
        return cleaned


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
