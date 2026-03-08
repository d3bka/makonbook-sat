from django.core.management.base import BaseCommand
from apps.sat.models import TestReview

class Command(BaseCommand):
    help = 'Sets all certificates to blank in all TestReviews'

    def handle(self, *args, **kwargs):
        reviews = TestReview.objects.all()
        for review in reviews:
            review.certificate = ''
            review.save()
        self.stdout.write(self.style.SUCCESS('Successfully set all certificates to blank'))
