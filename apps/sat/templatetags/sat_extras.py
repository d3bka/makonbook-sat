from django import template
from django.contrib.auth.models import User, Group
from apps.sat.models import Test, TestReview, TestStage

register = template.Library()

@register.simple_tag
def get_test_score(test, user):
    """
    Return the score for a given test and user.
    Returns score as a string or 'N/A' if not found.
    """
    try:
        review = TestReview.objects.get(test=test, user=user)
        return review.score
    except TestReview.DoesNotExist:
        return 'N/A'

@register.inclusion_tag('sat/tags/restart_button.html')
def render_restart_button(test, user, section=None):
    """
    Render a restart button for the given test and user.
    If section is provided, it will render a section-specific restart button.
    """
    is_allowed = False
    
    # Check if user is in OFFLINE or Admin group
    if user.groups.filter(name__in=['OFFLINE', 'Admin']).exists():
        is_allowed = True
    
    try:
        test_stage = TestStage.objects.get(user=user, test=test)
        can_restart = test_stage.again
    except TestStage.DoesNotExist:
        can_restart = False
        
    return {
        'test': test,
        'user': user,
        'section': section,
        'is_allowed': is_allowed,
        'can_restart': can_restart
    }

@register.inclusion_tag('sat/tags/score_display.html')
def show_test_score(test, user):
    """
    Render the score display for a test and user.
    """
    try:
        review = TestReview.objects.get(test=test, user=user)
        score = review.score
        return {
            'test': test,
            'score': score
        }
    except TestReview.DoesNotExist:
        return {
            'test': test,
            'score': None
        } 