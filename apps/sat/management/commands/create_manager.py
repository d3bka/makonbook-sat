from getpass import getpass

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Create or update a MakonBook Manager account and add it to the Manager group.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='manager')
        parser.add_argument('--password', default='')
        parser.add_argument('--email', default='')
        parser.add_argument('--first-name', default='MakonBook')
        parser.add_argument('--last-name', default='Manager')

    @transaction.atomic
    def handle(self, *args, **options):
        username = (options['username'] or '').strip()
        if not username:
            raise CommandError('Username cannot be empty.')

        password = options['password'] or ''
        if not password:
            if not self.stdin.isatty():
                raise CommandError('Pass --password when running non-interactively.')
            password = getpass(f'Password for {username}: ')
            confirm = getpass('Confirm password: ')
            if password != confirm:
                raise CommandError('Passwords do not match.')
        if len(password) < 8:
            raise CommandError('Password must contain at least 8 characters.')

        group, _ = Group.objects.get_or_create(name='Manager')
        user, created = User.objects.get_or_create(username=username)
        user.first_name = options['first_name']
        user.last_name = options['last_name']
        user.email = options['email']
        user.is_active = True
        # Manager is deliberately not Django staff/superuser. Access is scoped
        # through the Manager group and the dedicated manager dashboard.
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()
        user.groups.add(group)

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} manager account: {username}'))
        self.stdout.write('Login redirects to /sat/manager/.')
