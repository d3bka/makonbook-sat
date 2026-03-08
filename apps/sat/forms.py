from django import forms
from .models import English_Question, Math_Question, QuestionType

class EnglishQuestionForm(forms.ModelForm):
    class Meta:
        model = English_Question
        fields = '__all__'
        widgets = {
            'name': forms.Textarea(attrs={'onchange': 'this.form.submit();'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'type' in self.fields:
            self.fields['type'].queryset = QuestionType.objects.none()  # Initially empty queryset

        if self.instance.pk:  # Check if instance exists (editing an object)
            try:
                self.fields['type'].queryset = self.instance.domain.questiontype_set.all()
            except:
                self.fields['type'].queryset = QuestionType.objects.none()  # Initially empty queryset


        elif 'domain' in self.data:
            try:
                domain_id = int(self.data.get('domain'))
                self.fields['type'].queryset = QuestionType.objects.filter(domain_id=domain_id)
            except (ValueError, TypeError):
                pass  # Invalid input or no domain selected

class MathQuestionForm(forms.ModelForm):
    class Meta:
        model = Math_Question
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['domain'].widget.attrs.update({'onchange': 'this.form.submit();'})
        if 'type' in self.fields:
            self.fields['type'].queryset = QuestionType.objects.none()  # Initially empty queryset

        if self.instance.pk:  # Check if instance exists (editing an object)
            try:
                self.fields['type'].queryset = self.instance.domain.questiontype_set.all()
            except:
                self.fields['type'].queryset = QuestionType.objects.none()  # Initially empty queryset

        elif 'domain' in self.data:
            try:
                domain_id = int(self.data.get('domain'))
                print(domain_id)
                self.fields['type'].queryset = QuestionType.objects.filter(domain_id=domain_id)
            except (ValueError, TypeError):
                pass  # Invalid input or no domain selected

