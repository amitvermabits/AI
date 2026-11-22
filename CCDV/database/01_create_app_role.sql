-- 01_create_app_role.sql
-- Run in pgAdmin connected to database 'postgres', as the postgres administrator.
-- Safe to rerun for an existing app role.
-- SECURITY: Replace the example password below with your own strong local password
-- BEFORE execution. Do NOT commit the real password to Git.

DO $setup$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'travel_buddy_app'
    ) THEN
        CREATE ROLE travel_buddy_app LOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END;
$setup$;

-- Change the placeholder first. Reset this file to placeholder after running.
ALTER ROLE travel_buddy_app
    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
         PASSWORD 'approle@12345';

GRANT CONNECT ON DATABASE ai_travel_buddy TO travel_buddy_app;

-- Verify role properties (password deliberately not displayed).
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
FROM pg_catalog.pg_roles
WHERE rolname = 'travel_buddy_app';
