from apps.sat.models import Response,Event
from django.core.management.base import BaseCommand
from satmakon.settings import BASE_DIR



class Command(BaseCommand):
    help = 'Copies all questions in questions'

    def handle(self, *args, **options):
        events = Event.objects.all()
        for event in events:
            datas = Response.objects.filter(event=event)
            file = open(f'{event.name}','w')
            for data in datas:
                file.write(f'\nUsername is {data.user.username}\n{data.text}\n----------------------------------------')