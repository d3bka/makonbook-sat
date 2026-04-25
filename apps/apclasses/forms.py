from django import forms

from apps.sat.forms import SATEditorTextarea, SAT_HELP, IMAGE_HELP, CHOICE_IMAGE_HELP
from .models import APMultipleChoiceQuestion


class APMultipleChoiceQuestionForm(forms.ModelForm):
    textarea_fields = {
        'passage': ('passage', 8),
        'question': ('question', 6),
        'a': ('choice', 3),
        'b': ('choice', 3),
        'c': ('choice', 3),
        'd': ('choice', 3),
        'e': ('choice', 3),
        'explanation': ('explanation', 8),
    }

    class Meta:
        model = APMultipleChoiceQuestion
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
                self.fields[field_name].required = False

        if 'question' in self.fields:
            self.fields['question'].help_text = SAT_HELP
            self.fields['question'].widget.attrs['placeholder'] = (
                'Example: What is the value of \\(x\\) if \\(2x + 5 = 17\\)?'
            )

        if 'passage' in self.fields:
            self.fields['passage'].help_text = (
                'Use normal text and optional LaTeX. Keep line breaks clean. '
                'For AP question sets, paste the text directly instead of uploading it as an image.'
            )
            self.fields['passage'].widget.attrs['placeholder'] = (
                'Paste the shared stem or setup here. Use the keyboard below for symbols or formula templates.'
            )

        for field_name, label in [('a', 'Choice A'), ('b', 'Choice B'), ('c', 'Choice C'), ('d', 'Choice D'), ('e', 'Choice E')]:
            if field_name in self.fields:
                self.fields[field_name].help_text = (
                    f'{label}: plain text or LaTeX. Example: \\(\\frac{{x+2}}{{3}}\\)'
                )
                self.fields[field_name].widget.attrs['placeholder'] = f'{label}. Example: \\(\\frac{{x+2}}{{3}}\\)'

        if 'explanation' in self.fields:
            self.fields['explanation'].help_text = (
                'Solution or explanation. You can use the same SAT-style symbols, superscripts, subscripts, and LaTeX here.'
            )

        if 'image' in self.fields:
            self.fields['image'].help_text = IMAGE_HELP

        for field_name in ['image_a', 'image_b', 'image_c', 'image_d', 'image_e']:
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
            self.add_error(
                'image',
                'Keep the prompt in the Question field. Use the image only for a real figure, graph, table, or diagram.'
            )

        return cleaned_data
