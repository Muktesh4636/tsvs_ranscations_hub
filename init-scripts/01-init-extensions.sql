-- Database initialization script
-- This runs when the PostgreSQL container is first created

-- Enable necessary extensions for Django and performance
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_buffercache";

-- Create a role for the application (optional, for additional security)
-- DO $$
-- BEGIN
--    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'chip_app_role') THEN
--       CREATE ROLE chip_app_role;
--    END IF;
-- END
-- $$;

-- Set up basic database configuration
-- These can be adjusted based on your server resources
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET pg_stat_statements.max = 10000;
ALTER SYSTEM SET pg_stat_statements.track = 'all';

-- Performance tuning (adjust based on your server specs)
-- For a small server (2GB RAM, 2 cores):
ALTER SYSTEM SET work_mem = '8MB';
ALTER SYSTEM SET maintenance_work_mem = '128MB';
ALTER SYSTEM SET effective_cache_size = '512MB';
ALTER SYSTEM SET shared_buffers = '256MB';

-- For larger servers, uncomment and adjust:
-- ALTER SYSTEM SET work_mem = '16MB';
-- ALTER SYSTEM SET maintenance_work_mem = '256MB';
-- ALTER SYSTEM SET effective_cache_size = '1GB';
-- ALTER SYSTEM SET shared_buffers = '512MB';

-- Logging configuration
ALTER SYSTEM SET log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h ';
ALTER SYSTEM SET log_statement = 'ddl';
ALTER SYSTEM SET log_duration = on;

-- Note: You need to restart PostgreSQL for these settings to take effect
-- This will happen automatically on first container start