"""
Management command to create or update the logs viewer user (muktesh).
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create or update the logs viewer user (muktesh)'

    def handle(self, *args, **options):
        username = 'muktesh'
        password = 'muktesh123'
        email = 'muktesh@example.com'  # Optional email
        
        try:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'is_active': True,
                    'is_staff': False,
                    'is_superuser': False,
                }
            )
            
            # Set password (always update password to ensure it's correct)
            user.set_password(password)
            user.save()
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully created logs viewer user: {username}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Updated password for existing logs viewer user: {username}'
                    )
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Username: {username}\n'
                    f'Password: {password}\n'
                    f'Status: Active\n'
                    f'Access: Logs Dashboard only'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating/updating user: {str(e)}')
            )
