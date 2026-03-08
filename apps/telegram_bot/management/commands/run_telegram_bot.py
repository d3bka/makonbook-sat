import asyncio
import logging
from django.core.management.base import BaseCommand
from apps.telegram_bot.bot import main


class Command(BaseCommand):
    help = 'Run the MakonBook Telegram Bot for user management'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug logging',
        )
    
    def handle(self, *args, **options):
        if options['debug']:
            logging.basicConfig(level=logging.DEBUG)
        
        self.stdout.write(
            self.style.SUCCESS('Starting MakonBook Telegram Bot...')
        )
        
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('Bot stopped by user')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Bot error: {e}')
            )