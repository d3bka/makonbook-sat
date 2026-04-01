from django import forms
from django.utils.safestring import mark_safe

from .models import English_Question, Math_Question, QuestionType


SAT_HELP = mark_safe(
    "Write the question as text, not as a screenshot. "
    "Use the keyboard under the field for SAT symbols, superscripts, subscripts, Greek letters, and LaTeX templates. "
    r"You can still type formulas directly with delimiters like \(x^2+5x+6=0\) or \[\frac{a+b}{c}\]."
)

IMAGE_HELP = (
    "Upload only real diagrams, graphs, tables, coordinate planes, or figures. "
    "Do not upload a screenshot of the whole question. The question text must stay in the text field."
)

CHOICE_IMAGE_HELP = (
    "Use this only when the answer choice itself is an actual image or graph. "
    "Do not convert text choices into screenshots."
)


class SATEditorTextarea(forms.Textarea):
    """Textarea enhanced in Django admin with a sectioned SAT keyboard and live preview."""

    def __init__(self, *args, field_role='general', **kwargs):
        attrs = kwargs.pop('attrs', {}) or {}
        attrs.setdefault('class', 'vLargeTextField sat-editor-textarea')
        attrs.setdefault('data-sat-editor', '1')
        attrs.setdefault('data-sat-role', field_role)
        attrs.setdefault('spellcheck', 'false')
        attrs.setdefault('autocomplete', 'off')
        attrs.setdefault('autocapitalize', 'off')
        attrs.setdefault('autocorrect', 'off')
        super().__init__(attrs=attrs, *args, **kwargs)

    class Media:
        css = {
            'all': (
                'https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css',
                'admin/css/sat-question-editor.css',
            )
        }
        js = (
            'https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js',
            'https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js',
            'admin/js/sat-question-editor.js',
        )


class BaseQuestionForm(forms.ModelForm):
    long_text_rows = 6
    choice_rows = 3
    explanation_rows = 8

    textarea_fields = {
        'passage': ('passage', 10),
        'question': ('question', long_text_rows),
        'a': ('choice', choice_rows),
        'b': ('choice', choice_rows),
        'c': ('choice', choice_rows),
        'd': ('choice', choice_rows),
        'explained': ('explanation', explanation_rows),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'domain' in self.fields:
            self.fields['domain'].widget.attrs.update({'onchange': 'this.form.submit();'})

        if 'type' in self.fields:
            self.fields['type'].queryset = QuestionType.objects.none()

        if self.instance.pk and getattr(self.instance, 'domain', None):
            self.fields['type'].queryset = self.instance.domain.questiontype_set.all()
        elif 'domain' in self.data:
            try:
                domain_id = int(self.data.get('domain'))
                self.fields['type'].queryset = QuestionType.objects.filter(domain_id=domain_id)
            except (ValueError, TypeError):
                self.fields['type'].queryset = QuestionType.objects.none()

        for field_name, config in self.textarea_fields.items():
            if field_name in self.fields:
                role, rows = config
                self.fields[field_name].widget = SATEditorTextarea(
                    field_role=role,
                    attrs={
                        'rows': rows,
                        'style': 'width: 95%; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;',
                    },
                )

        for field_name in ['passage', 'question', 'a', 'b', 'c', 'd', 'explained']:
            if field_name in self.fields:
                self.fields[field_name].required = False

        if 'question' in self.fields:
            self.fields['question'].help_text = SAT_HELP
            self.fields['question'].widget.attrs['placeholder'] = (
                'Example: What is the value of \\(x\\) if \\(2x + 5 = 17\\)?'
            )

        if 'passage' in self.fields:
            self.fields['passage'].help_text = (
                'Use normal text and optional LaTeX. Keep line breaks clean. '
                'For reading passages, paste the text directly instead of uploading it as an image.'
            )
            self.fields['passage'].widget.attrs['placeholder'] = (
                'Paste the passage here. Use the keyboard below for symbols or formula templates.'
            )

        for field_name, label in [('a', 'Choice A'), ('b', 'Choice B'), ('c', 'Choice C'), ('d', 'Choice D')]:
            if field_name in self.fields:
                self.fields[field_name].help_text = (
                    f'{label}: plain text or LaTeX. Example: \\(\\frac{{x+2}}{{3}}\\)'
                )
                self.fields[field_name].widget.attrs['placeholder'] = f'{label}. Example: \\(\\frac{{x+2}}{{3}}\\)'

        if 'explained' in self.fields:
            self.fields['explained'].help_text = (
                'Solution or explanation. You can use SAT symbols, superscripts, subscripts, and LaTeX here.'
            )

        if 'image' in self.fields:
            self.fields['image'].help_text = IMAGE_HELP

        for field_name in ['image_a', 'image_b', 'image_c', 'image_d', 'img_explain']:
            if field_name in self.fields:
                self.fields[field_name].help_text = CHOICE_IMAGE_HELP

    def clean(self):
        cleaned_data = super().clean()

        question_text = (cleaned_data.get('question') or '').strip()
        question_image = cleaned_data.get('image')

        if question_image and not question_text:
            self.add_error(
                'question',
                'Question text is required. Images are supplemental only; do not upload the whole question as a screenshot.'
            )

        if 'image' in self.fields and question_image and not question_text:
            self.add_error(
                'image',
                'Keep the prompt in the Question field. Use the image only for a real figure, graph, table, or diagram.'
            )

        if 'choice_graph' in self.fields:
            choice_images_present = any(
                cleaned_data.get(name)
                for name in ['image_a', 'image_b', 'image_c', 'image_d']
                if name in self.fields
            )
            choice_graph = cleaned_data.get('choice_graph')
            if choice_images_present and not choice_graph:
                self.add_error(
                    'choice_graph',
                    'Turn on "Is there Graph or Table in choices" when uploading image-based choices.'
                )

        return cleaned_data


class EnglishQuestionForm(BaseQuestionForm):
    class Meta:
        model = English_Question
        fields = '__all__'


class MathQuestionForm(BaseQuestionForm):
    class Meta:
        model = Math_Question
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'answer' in self.fields:
            self.fields['answer'].required = False
            self.fields['answer'].widget = SATEditorTextarea(
                field_role='answer',
                attrs={
                    'rows': 2,
                    'style': 'width: 95%; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;',
                    'placeholder': 'Written answer. Example: \\(\\frac{3}{2}\\) or 7',
                },
            )
            self.fields['answer'].help_text = (
                'For written-response math questions, type the answer as text or LaTeX. '
                'Use the keyboard below for quick superscripts, subscripts, fractions, and symbols.'
            )
