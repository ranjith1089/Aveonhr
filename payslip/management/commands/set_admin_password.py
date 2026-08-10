"""Management command to set/reset admin password."""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Set or reset admin password'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to reset password for')
        parser.add_argument('password', type=str, help='New password')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        try:
            user = User.objects.get(username=username)
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Password set for {username}\n'
                    f'You can now login with:\n'
                    f'  Username: {username}\n'
                    f'  Password: {password}'
                )
            )
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User {username} not found!')
            )
