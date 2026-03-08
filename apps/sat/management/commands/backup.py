import os
import shutil
import datetime
from django.core.management.base import BaseCommand
from satmakon.settings import BASE_DIR

class Command(BaseCommand):
    help = 'Back up the db.sqlite3 file'

    def handle(self, *args, **options):
        today = datetime.date.today()
        backup_folder = BASE_DIR / f"backups/{today.strftime('%Y-%m-%d')}"
        os.makedirs(backup_folder, exist_ok=True)

        db_file = BASE_DIR / 'db.sqlite3'
        backup_path = backup_folder/'db.sqlite3'

        shutil.copy(db_file, backup_path)
        self.stdout.write(self.style.SUCCESS(f'Successfully backed up the database to {backup_path}'))