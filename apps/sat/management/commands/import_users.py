import random
import string
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

class Command(BaseCommand):
    help = 'Import users with course preferences and generate random usernames and passwords, then save to a txt file.'

    def add_arguments(self, parser):
        parser.add_argument('num_users', type=int, help='Number of users to create')
        parser.add_argument('name_prefix', type=str, help='Prefix for usernames (e.g., name1, name2)')
        parser.add_argument('group_pk', type=int, help='Primary key of the group to assign the users to')
        parser.add_argument('--offline', action='store_true', help='Add users to the OFFLINE group')

    def handle(self, *args, **options):
        num_users = options['num_users']
        name_prefix = options['name_prefix']
        group_pk = options['group_pk']
        is_offline = options['offline']
        
        try:
            group = Group.objects.get(pk=group_pk)
        except Group.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Group with pk {group_pk} does not exist.'))
            return
        
        # Get OFFLINE group if needed
        offline_group = None
        if is_offline:
            try:
                offline_group = Group.objects.get(name='OFFLINE')
                self.stdout.write(self.style.SUCCESS(f'Found OFFLINE group'))
            except Group.DoesNotExist:
                self.stdout.write(self.style.ERROR('OFFLINE group does not exist. Creating it...'))
                offline_group = Group.objects.create(name='OFFLINE')
        
        users_data = []

        for i in range(1, num_users + 1):
            # Generate a random password
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            username = f"{name_prefix}{i}"
            
            # Create the user
            user = User.objects.create_user(username=username, password=password)
            
            # Assign user to the specified group
            user.groups.add(group)
            
            # Add to OFFLINE group if requested
            if is_offline and offline_group:
                user.groups.add(offline_group)
                users_data.append(f"Username: {username}, Password: {password}, Groups: {group.name}, OFFLINE")
            else:
                users_data.append(f"Username: {username}, Password: {password}, Group: {group.name}")

        # Write the user credentials to a text file
        with open('user_logins.txt', 'w') as file:
            for user_data in users_data:
                file.write(f"{user_data}\n")

        offline_msg = " with OFFLINE access" if is_offline else ""
        self.stdout.write(self.style.SUCCESS(f'Successfully created {num_users} users{offline_msg} and saved their logins to user_logins.txt'))
