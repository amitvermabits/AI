"""AI Travel Buddy — Day 05, Lab 19: Durable trip memory in PostgreSQL.

Learning objectives
-------------------
CCDV-F: distinguish model context from durable external application memory.
CCAR-F: demonstrate tenant-scoped reads, transactional persistence, and
         trustworthy state restoration across separate Python processes.

The project uses the PostgreSQL server installed on your computer.
This lab does not call Claude or access any third-party travel service.

Install: uv add "psycopg[binary]" python-dotenv
Configure: TRAVEL_BUDDY_DATABASE_URL in the project root .env file.

Commands (run from the project root):
    uv run python -m app.agents.day05_lab19_postgres_trip_memory init
    uv run python -m app.agents.day05_lab19_postgres_trip_memory save
    uv run python -m app.agents.day05_lab19_postgres_trip_memory load
    uv run python -m app.agents.day05_lab19_postgres_trip_memory test

Lab note: 'init' performs simple initial DDL for learning. Production systems
should use version-controlled Alembic migrations and distinct DDL/runtime roles.
"""

from __future__ import annotations

import argparse
import os
import uuid
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SCHEMA = "travel_buddy_lab"
TABLE = f"{SCHEMA}.trip_preferences"
DEMO_USER_ID = "demo-user-001"
DEMO_TRIP_ID = "demo-trip-001"


@dataclass(frozen=True, slots=True)
class TripPreferences:
    """Validated, tenant-owned trip preferences for external memory storage."""

    user_id: str
    trip_id: str
    origin: str
    destination: str
    travelers: int
    budget_eur: Decimal
    preferences: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce basic application rules before any database write."""
        for field_name in ("user_id", "trip_id", "origin", "destination"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                raise ValueError(f"{field_name} must be a nonempty string of <=120 characters")
        if type(self.travelers) is not int or not 1 <= self.travelers <= 12:
            raise ValueError("travelers must be an integer from 1 to 12")
        if not isinstance(self.budget_eur, Decimal):
            raise TypeError("budget_eur must be Decimal for precise money handling")
        try:
            valid_budget = self.budget_eur.is_finite() and self.budget_eur > 0
        except InvalidOperation:
            valid_budget = False
        if not valid_budget or self.budget_eur.as_tuple().exponent < -2:
            raise ValueError("budget_eur must be positive with at most two decimal places")
        if not isinstance(self.preferences, dict):
            raise ValueError("preferences must be a JSON-compatible dictionary")


def database_url() -> str:
    """Read the connection string from the environment without printing secrets."""
    load_dotenv(override=True)
    url = os.getenv("TRAVEL_BUDDY_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "Set TRAVEL_BUDDY_DATABASE_URL in your project .env file first. "
            "Never commit passwords to Git."
        )
    return url


def connect() -> psycopg.Connection:
    """Open one short-lived transactional PostgreSQL connection."""
    return psycopg.connect(database_url(), connect_timeout=5, row_factory=dict_row)


def initialize_database() -> None:
    """Create a lab namespace and table; later replace with Alembic migrations.

    This requires a database role with CREATE privileges. For an actual service,
    provision schemas using a migration role and grant the app only DML rights.
    """
    with connect() as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                user_id VARCHAR(120) NOT NULL,
                trip_id VARCHAR(120) NOT NULL,
                origin VARCHAR(120) NOT NULL CHECK (length(trim(origin)) > 0),
                destination VARCHAR(120) NOT NULL CHECK (length(trim(destination)) > 0),
                travelers SMALLINT NOT NULL CHECK (travelers BETWEEN 1 AND 12),
                budget_eur NUMERIC(12, 2) NOT NULL CHECK (budget_eur > 0),
                preferences JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (user_id, trip_id)
            )
            """
        )
    print("[INIT] PostgreSQL schema and trip_preferences table are ready.")


def save_trip(trip: TripPreferences) -> None:
    """Upsert preferences atomically; identify trips by BOTH owner and trip ID."""
    with connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {TABLE}
                (user_id, trip_id, origin, destination,
                 travelers, budget_eur, preferences)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, trip_id)
            DO UPDATE SET
                origin = EXCLUDED.origin,
                destination = EXCLUDED.destination,
                travelers = EXCLUDED.travelers,
                budget_eur = EXCLUDED.budget_eur,
                preferences = EXCLUDED.preferences,
                updated_at = now()
            """,
            (
                trip.user_id, trip.trip_id, trip.origin, trip.destination,
                trip.travelers, trip.budget_eur, Jsonb(trip.preferences),
            ),
        )
    # Exiting the connection context commits when no exception occurred.


def load_trip(user_id: str, trip_id: str) -> TripPreferences | None:
    """Retrieve a trip only by a trusted, authenticated user scope.

    This lab's caller supplies user_id directly. A production API MUST derive
    user_id from verified authentication, never accept it from Claude text.
    """
    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT user_id, trip_id, origin, destination,
                   travelers, budget_eur, preferences
            FROM {TABLE}
            WHERE user_id = %s AND trip_id = %s
            """,
            (user_id, trip_id),
        ).fetchone()
    return TripPreferences(**row) if row else None


def remove_test_trips(user_ids: list[str]) -> None:
    """Remove only unique, randomly tagged test identities used by this lab."""
    with connect() as conn:
        conn.execute(
            f"DELETE FROM {TABLE} WHERE user_id = ANY(%s)",
            (user_ids,),
        )


def demo_trip() -> TripPreferences:
    """Return fictitious data for two-process persistence demonstration."""
    return TripPreferences(
        user_id=DEMO_USER_ID,
        trip_id=DEMO_TRIP_ID,
        origin="Toulouse",
        destination="Paris",
        travelers=4,
        budget_eur=Decimal("300.00"),
        preferences={"transport_preference": "train", "source": "demo"},
    )


def run_self_tests() -> None:
    """Exercise persistence, user isolation, updates and validation.

    Uses random test users and cleans up only their records. Each read/write
    creates a separate connection; this checks actual database persistence.
    """
    run_id = uuid.uuid4().hex[:12]
    user_a, user_b = f"test-a-{run_id}", f"test-b-{run_id}"
    trip_id = f"test-trip-{run_id}"
    print("[TEST] Using isolated fictional test identities")
    try:
        original = replace(demo_trip(), user_id=user_a, trip_id=trip_id)
        save_trip(original)
        assert load_trip(user_a, trip_id) == original
        print("[PASS] Saved data survives separate PostgreSQL connections")

        assert load_trip(user_b, trip_id) is None
        print("[PASS] A different user cannot read this trip through the scoped query")

        changed = replace(original, budget_eur=Decimal("450.50"))
        save_trip(changed)
        assert load_trip(user_a, trip_id) == changed
        assert load_trip(user_a, "nonexistent-trip") is None
        print("[PASS] Upsert updates one trip; missing trip returns None")

        try:
            replace(original, travelers=0)
        except ValueError:
            print("[PASS] Invalid traveler count rejected before database write")
        else:
            raise AssertionError("Invalid traveler count unexpectedly accepted")

        print("LAB 19: ALL 4 POSTGRESQL TESTS PASSED")
    finally:
        remove_test_trips([user_a, user_b])
        print("[CLEANUP] Test records removed; demo data left untouched")


def main() -> None:
    """Run a requested lab operation, returning clear non-secret error details."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "save", "load", "test"])
    args = parser.parse_args()

    try:
        if args.command == "init":
            initialize_database()
        elif args.command == "save":
            save_trip(demo_trip())
            print("[SAVE] Demo preferences persisted to PostgreSQL")
        elif args.command == "load":
            trip = load_trip(DEMO_USER_ID, DEMO_TRIP_ID)
            if trip is None:
                print("[LOAD] No demo trip found. Run 'save' first.")
            else:
                print(f"[LOAD] {trip.origin} -> {trip.destination}")
                print(f"[LOAD] Travelers: {trip.travelers}")
                print(f"[LOAD] Budget (EUR): {trip.budget_eur}")
                print(f"[LOAD] Preferences: {trip.preferences}")
        else:
            run_self_tests()
    except psycopg.OperationalError:
        raise SystemExit(
            "PostgreSQL connection failed. Check that the server is running, "
            "the database and role exist, and the .env connection URL is correct."
        ) from None
    except psycopg.errors.InsufficientPrivilege:
        raise SystemExit(
            "Database role lacks privileges. Grant the needed schema/table "
            "permissions or use a dedicated migration role for 'init'."
        ) from None


if __name__ == "__main__":
    main()
