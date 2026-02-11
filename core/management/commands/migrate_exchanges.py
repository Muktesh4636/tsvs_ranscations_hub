"""
Management command to migrate exchanges from pravoo.in to svs.transactions
Usage: python manage.py migrate_exchanges
"""
from django.core.management.base import BaseCommand
from core.models import Exchange


class Command(BaseCommand):
    help = 'Migrate exchanges from pravoo.in to svs.transactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--exchanges',
            nargs='+',
            help='List of exchange names to add (space-separated)',
        )
        parser.add_argument(
            '--from-file',
            type=str,
            help='Path to file containing exchange data (one per line, format: name|code|version)',
        )

    def handle(self, *args, **options):
        # Common exchanges that might exist in pravoo.in
        # You can update this list based on what you see in pravoo.in
        default_exchanges = [
            # Format: (name, code, version_name)
            # Add exchanges from pravoo.in here
            # Example: ('Taj Exchange', 'taj', 'v1'),
        ]

        exchanges_to_add = []
        
        if options['exchanges']:
            # Add exchanges from command line arguments
            for exchange_name in options['exchanges']:
                exchanges_to_add.append((exchange_name, None, None))
        elif options['from_file']:
            # Read from file
            try:
                with open(options['from_file'], 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('|')
                        name = parts[0].strip()
                        code = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
                        version = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
                        exchanges_to_add.append((name, code, version))
            except FileNotFoundError:
                self.stdout.write(self.style.ERROR(f'File not found: {options["from_file"]}'))
                return
        else:
            # Use default list (you should update this with actual exchanges from pravoo.in)
            exchanges_to_add = default_exchanges
            if not exchanges_to_add:
                self.stdout.write(self.style.WARNING(
                    'No exchanges specified. Use --exchanges or --from-file, or update default_exchanges in the script.'
                ))
                self.stdout.write(self.style.SUCCESS('\nCurrent exchanges in database:'))
                existing = Exchange.objects.all()
                for e in existing:
                    self.stdout.write(f'  - {e.name} (code: {e.code or "N/A"}, version: {e.version_name or "N/A"})')
                return

        # Display current exchanges
        self.stdout.write(self.style.SUCCESS('\nCurrent exchanges in database:'))
        existing = Exchange.objects.all()
        existing_names = {e.name.lower(): e for e in existing}
        self.stdout.write(f'Total: {existing.count()}')
        for e in existing:
            self.stdout.write(f'  - {e.name} (code: {e.code or "N/A"}, version: {e.version_name or "N/A"})')

        # Add new exchanges
        added_count = 0
        skipped_count = 0
        
        self.stdout.write(self.style.SUCCESS(f'\nAdding {len(exchanges_to_add)} exchange(s)...'))
        
        for name, code, version in exchanges_to_add:
            # Check if exchange already exists (case-insensitive)
            if name.lower() in existing_names:
                self.stdout.write(self.style.WARNING(f'  Skipping "{name}" - already exists'))
                skipped_count += 1
                continue
            
            try:
                exchange = Exchange.objects.create(
                    name=name,
                    code=code,
                    version_name=version
                )
                self.stdout.write(self.style.SUCCESS(f'  ✓ Added: {name}' + 
                    (f' (code: {code})' if code else '') + 
                    (f' (version: {version})' if version else '')))
                added_count += 1
                existing_names[name.lower()] = exchange
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error adding "{name}": {str(e)}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nMigration complete! Added: {added_count}, Skipped: {skipped_count}'
        ))
