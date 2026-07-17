from decimal import Decimal

from django import forms

from .models import RatingAssessment


class RatingAssessmentForm(forms.ModelForm):
    class Meta:
        model = RatingAssessment
        fields = ["homework", "progress", "activity", "attendance", "behavior", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["homework", "progress", "activity", "attendance", "behavior"]:
            self.fields[name].widget = forms.NumberInput(attrs={"min": "0", "max": "10", "step": "0.5", "inputmode": "decimal"})
            self.fields[name].initial = self.fields[name].initial or Decimal("8.0")
