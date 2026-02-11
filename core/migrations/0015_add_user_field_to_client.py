# Generated manually to fix migration order issue
# This migration adds the user field to Client after CustomUser exists

# Generated manually
# NOTE: Client.user field is now created in 0001_initial.py
# This migration is kept for historical consistency but does nothing

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_mobilelog_alter_transaction_options_and_more'),
    ]

    operations = [
        # Client.user field is now created in 0001_initial.py
        # This migration is kept for historical consistency but does nothing
    ]
