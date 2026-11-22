# AI Travel Buddy — PostgreSQL setup for Lab 19

The SQL matches `app/agents/day05_lab19_postgres_trip_memory.py`.

## Run order in pgAdmin

1. **00_optional_create_database.sql** — SKIP: you already created `ai_travel_buddy`.
   If recreating from scratch, execute it *only* on the maintenance `postgres` database,
   as an admin, and outside of an explicit transaction.
2. **01_create_app_role.sql** — Open Query Tool connected to the `postgres` database,
   as an administrator. Replace the placeholder password with a strong local password,
   then run the script. **Never commit the real password**. Restore the placeholder
   in the file after execution.
3. **02_schema_and_seed.sql** — Open a new Query Tool connected to the
   `ai_travel_buddy` database, as `postgres` administrator. Run the entire script.

## Python

In the project's `.env` (gitignored):

    TRAVEL_BUDDY_DATABASE_URL=postgresql://travel_buddy_app:URL_ENCODED_PASSWORD@localhost:5432/ai_travel_buddy

Use percent encoding for reserved characters in the connection URL's password.
Install driver:

    uv add "psycopg[binary]" python-dotenv

Since the admin script **already creates schema and table**, do NOT run Lab 19's
`init` command with `travel_buddy_app`. It intentionally lacks DDL privileges.

Run these from the project root:

    uv run python -m app.agents.day05_lab19_postgres_trip_memory load
    uv run python -m app.agents.day05_lab19_postgres_trip_memory save
    uv run python -m app.agents.day05_lab19_postgres_trip_memory test

`load` should already show demo-user-001 / demo-trip-001, Toulouse -> Paris,
four travelers and budget EUR 300. Lab 19 `test` creates temporary
random test identities and cleans them up.

## Production architecture notes

- **Security:** the Python runtime role has USAGE on one schema and only
  SELECT/INSERT/UPDATE/DELETE on one table; no DDL or superuser privileges.
- **Data isolation:** the demo Python code filters on `(user_id, trip_id)` but
  this is NOT sufficient database-enforced tenant isolation. For production:
  derive identity from verified authentication; consider PostgreSQL row-level
  security (RLS) and separate DB roles or a trusted tenant context.
- **Reliability:** the composite primary key supports idempotent upsert.
- **Repeatability:** these scripts are rerunnable for a clean lab environment;
  use Alembic migrations in production.
- **Observability:** add structured audit logs / traces, avoiding PII and
  secrets in application logs.
- **Cost:** local PostgreSQL is free to run (hardware and operational
  effort still have costs).

All data in seed scripts is fictional; do not treat it as a live fare or booking.
