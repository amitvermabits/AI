-- 02_schema_and_seed.sql
-- Run in pgAdmin CONNECTED TO ai_travel_buddy as postgres administrator.
-- Matches app/agents/day05_lab19_postgres_trip_memory.py exactly.
-- Idempotent: CREATE IF NOT EXISTS and INSERT ON CONFLICT DO NOTHING.
-- WARNING: Do not use this seed against a database holding real customer records.

BEGIN;

-- Administrator owns DDL. The runtime login receives no CREATE permission.
CREATE SCHEMA IF NOT EXISTS travel_buddy_lab AUTHORIZATION postgres;

CREATE TABLE IF NOT EXISTS travel_buddy_lab.trip_preferences (
    user_id VARCHAR(120) NOT NULL,
    trip_id VARCHAR(120) NOT NULL,
    origin VARCHAR(120) NOT NULL CHECK (length(trim(origin)) > 0),
    destination VARCHAR(120) NOT NULL CHECK (length(trim(destination)) > 0),
    travelers SMALLINT NOT NULL CHECK (travelers BETWEEN 1 AND 12),
    budget_eur NUMERIC(12, 2) NOT NULL CHECK (budget_eur > 0),
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(preferences) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, trip_id)
);

-- Separate DDL privileges from normal application DML.
GRANT USAGE ON SCHEMA travel_buddy_lab TO travel_buddy_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE travel_buddy_lab.trip_preferences TO travel_buddy_app;

-- Fictional, intentionally non-PII test data.
-- First seed matches the Lab 19 Python demo_trip() identifiers and values.
INSERT INTO travel_buddy_lab.trip_preferences
    (user_id, trip_id, origin, destination, travelers, budget_eur, preferences)
VALUES
    (
        'demo-user-001', 'demo-trip-001',
        'Toulouse', 'Paris', 4, 300.00,
        '{"transport_preference":"train","source":"demo"}'::jsonb
    ),
    (
        'demo-user-001', 'demo-trip-002',
        'Toulouse', 'Strasbourg', 4, 700.00,
        '{"transport_preference":"train","family_friendly":true,"travel_dates":{"start":"2026-12-20","end":"2026-12-23"},"source":"seed"}'::jsonb
    ),
    (
        'demo-user-002', 'demo-trip-001',
        'Lyon', 'Nice', 2, 450.50,
        '{"transport_preference":"train","accommodation":"apartment","source":"seed"}'::jsonb
    ),
    (
        'demo-user-003', 'demo-trip-001',
        'Bordeaux', 'Barcelona', 1, 250.00,
        '{"transport_preference":"bus","budget_sensitive":true,"source":"seed"}'::jsonb
    )
ON CONFLICT (user_id, trip_id) DO NOTHING;

COMMIT;

-- Confirm the seeded preferences, including JSONB.
SELECT user_id, trip_id, origin, destination,
       travelers, budget_eur, preferences
FROM travel_buddy_lab.trip_preferences
ORDER BY user_id, trip_id;

-- Inspect key permissions. Expected: SELECT true, CREATE on schema false.
SELECT
    has_schema_privilege(
        'travel_buddy_app', 'travel_buddy_lab', 'USAGE'
    ) AS schema_usage,
    has_schema_privilege(
        'travel_buddy_app', 'travel_buddy_lab', 'CREATE'
    ) AS schema_create,
    has_table_privilege('travel_buddy_app', 'travel_buddy_lab.trip_preferences', 'SELECT')
    AND has_table_privilege('travel_buddy_app', 'travel_buddy_lab.trip_preferences', 'INSERT')
    AND has_table_privilege('travel_buddy_app', 'travel_buddy_lab.trip_preferences', 'UPDATE')
    AND has_table_privilege('travel_buddy_app', 'travel_buddy_lab.trip_preferences', 'DELETE')
    AS table_read_write;
