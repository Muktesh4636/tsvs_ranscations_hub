# Database Initialization Scripts

These SQL scripts run automatically when the PostgreSQL container is first created. They set up:

- Required PostgreSQL extensions for Django
- Basic performance tuning for your server specs
- Logging configuration

## Files

- `01-init-extensions.sql` - Basic database setup and performance tuning

## Customization

Edit the values in `01-init-extensions.sql` based on your server resources:

### For Small Servers (2GB RAM, 2 cores)
```sql
work_mem = '8MB'
maintenance_work_mem = '128MB'
effective_cache_size = '512MB'
shared_buffers = '256MB'
```

### For Medium Servers (4GB RAM, 4 cores)
```sql
work_mem = '16MB'
maintenance_work_mem = '256MB'
effective_cache_size = '2GB'
shared_buffers = '1GB'
```

### For Large Servers (8GB+ RAM, 8+ cores)
```sql
work_mem = '32MB'
maintenance_work_mem = '512MB'
effective_cache_size = '4GB'
shared_buffers = '2GB'
```

## Adding Custom Scripts

To add more initialization scripts:
1. Create a new `.sql` file with a numbered prefix (02-, 03-, etc.)
2. Place it in this directory
3. The scripts will run in alphabetical order

Example: `02-create-custom-functions.sql`