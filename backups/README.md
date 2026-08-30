# Database Backups

## Latest Backup: 2026-03-06 19:04:28

### Newest Backup Files:

1. **django_backup_20260306_190428.json** (~20K)
   - Django JSON format backup
   - Contains all Django model data (exchanges, clients, accounts, etc.)
   - Restore: `python manage.py loaddata backups/django_backup_20260306_190428.json`

2. **postgres_backup_20260306_190428.sql** (~61K)
   - PostgreSQL SQL text format backup
   - Human-readable, complete database
   - Restore: `psql -h localhost -U postgres -d broker_portal < backups/postgres_backup_20260306_190428.sql`

---

## Previous Backup: 2026-01-15 18:10:42

### Backup Files:

1. **django_backup_20260115_181042.json** (21K)
   - Django JSON format backup
   - Contains all Django model data
   - Can be restored using: `python manage.py loaddata django_backup_20260115_181042.json`

2. **postgres_backup_20260115_181042.dump** (58K)
   - PostgreSQL custom format backup (compressed)
   - Complete database backup including schema and data
   - Can be restored using: `pg_restore -h localhost -U postgres -d broker_portal -c postgres_backup_20260115_181042.dump`

3. **postgres_backup_20260115_181042.sql** (55K)
   - PostgreSQL SQL text format backup
   - Human-readable SQL dump
   - Can be restored using: `psql -h localhost -U postgres -d broker_portal < postgres_backup_20260115_181042.sql`

### Database Information:
- Database Name: broker_portal
- Database User: postgres
- Database Host: localhost
- Database Port: 5432

### Total Backup Size: 144K

### Restore Instructions:

#### Using Django JSON backup:
```bash
cd /root/Chips_dashboard
source myenv/bin/activate
python manage.py loaddata backups/django_backup_20260115_181042.json
```

#### Using PostgreSQL custom dump:
```bash
cd /root/Chips_dashboard
PGPASSWORD=<your_password> pg_restore -h localhost -U postgres -d broker_portal -c backups/postgres_backup_20260115_181042.dump
```

#### Using PostgreSQL SQL dump:
```bash
cd /root/Chips_dashboard
PGPASSWORD=<your_password> psql -h localhost -U postgres -d broker_portal < backups/postgres_backup_20260115_181042.sql
```

**Note:** Replace `<your_password>` with your actual PostgreSQL password, or ensure your `.env` file has the correct `DB_PASSWORD` configured.
