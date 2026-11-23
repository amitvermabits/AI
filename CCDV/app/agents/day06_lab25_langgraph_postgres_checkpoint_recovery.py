"""Day 06 / Lab 25 — LangGraph durable checkpointing across Python process restarts.

Learning goal
-------------
Lab 24 used InMemorySaver. Here the SAME graph is compiled with PostgresSaver,
so a pause made by one Python process can be resumed by a DIFFERENT process.

This is a safe AI Travel Buddy simulation: no Claude invocation, payment, real
booking, network travel search, or mutation of Lab 19's trip_preferences.

Prerequisites
-------------
1. Existing local PostgreSQL database and `travel_buddy_app` login from Lab 19.
2. Project-root .env has TRAVEL_BUDDY_DATABASE_URL=<your role connection URL>.
3. Install once: uv add langgraph langgraph-checkpoint-postgres "psycopg[binary]" python-dotenv

Commands (from the project root)
--------------------------------
One-time privileged schema creation, as local PostgreSQL administrator:
    uv run python -m app.agents.day06_lab25_langgraph_postgres_checkpoint_recovery setup

Start the approval workflow and STOP the Python process:
    uv run python -m app.agents.day06_lab25_langgraph_postgres_checkpoint_recovery pause --thread lab25-trip-001

Check the persisted state in a NEW Python process:
    uv run python -m app.agents.day06_lab25_langgraph_postgres_checkpoint_recovery status --thread lab25-trip-001

Resume and complete the workflow in ANOTHER process:
    uv run python -m app.agents.day06_lab25_langgraph_postgres_checkpoint_recovery resume --thread lab25-trip-001 --decision approve

Try a separate new thread with --decision reject. For a fresh pause, choose a
new thread ID. A thread is intentionally not silently overwritten.

Offline behavior checks (no PostgreSQL needed):
    uv run python -m app.agents.day06_lab25_langgraph_postgres_checkpoint_recovery test

Production note
---------------
PostgresSaver stores opaque graph state in checkpoint tables; it does NOT
provide per-user database Row-Level Security. This exercise uses a single local
app login. Production must authorize the requested thread_id against an
authenticated tenant and protect/expire checkpoint records appropriately.
"""

from __future__ import annotations

import argparse
import getpass
import os
from typing import Any, TypedDict

import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

# A dedicated namespace keeps execution checkpoints separate from Lab 19 trip
# memory (travel_buddy_lab.trip_preferences). This is NOT a per-user namespace.
CHECKPOINT_SCHEMA = "travel_buddy_checkpoints"
CHECKPOINT_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
)


class TravelState(TypedDict):
    """A simple snapshot of progress through one fictional approval workflow."""

    destination: str
    phase: str
    approved: bool | None


def prepare(state: TravelState) -> dict[str, str]:
    """Prepare a fictional travel plan without performing any side effects."""
    if not state["destination"].strip():
        raise ValueError("A destination is required")
    return {"phase": "ready_for_approval"}


def approval_gate(state: TravelState) -> dict[str, str | bool]:
    """Pause until an authorized application supplies the approval decision.

    LangGraph re-enters this node on resume. Statements before interrupt()
    may run again, so none may charge, book, or mutate external resources.
    """
    decision = interrupt(
        {
            "question": "Approve this FICTIONAL travel plan?",
            "destination": state["destination"],
            "phase": state["phase"],
        }
    )
    if type(decision) is not bool:
        raise ValueError("Expected a real boolean approval decision")
    return {
        "approved": decision,
        "phase": "approved" if decision else "rejected",
    }


def finalize(state: TravelState) -> dict[str, str]:
    """Record the demonstration outcome. Never book or charge anything."""
    return {
        "phase": "demo_approved_no_booking"
        if state["approved"] is True
        else "demo_rejected_no_booking"
    }


def build_graph(checkpointer: Any) -> Any:
    """Compile the graph using the injected checkpoint backend.

    This graph is identical in structure for both InMemorySaver and PostgresSaver.
    Swapping the checkpointer changes durability, not workflow semantics.
    """
    builder = StateGraph(TravelState)
    builder.add_node("prepare", prepare)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "approval_gate")
    builder.add_edge("approval_gate", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def config_for(thread_id: str) -> dict[str, dict[str, str]]:
    """Use a stable thread identifier to locate one persisted execution."""
    if not thread_id or len(thread_id) > 120 or not thread_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("thread ID must be 1–120 letters, digits, dashes or underscores")
    return {"configurable": {"thread_id": thread_id}}


def database_url() -> str:
    """Read the existing Lab 19 app-role URL without ever displaying secrets."""
    load_dotenv(override=True)
    url = os.getenv("TRAVEL_BUDDY_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Missing TRAVEL_BUDDY_DATABASE_URL in project .env")
    return url


def app_role_name(url: str) -> str:
    """Extract the configured PostgreSQL username for precise GRANT commands."""
    role = conninfo_to_dict(url).get("user", "")
    if not role:
        raise ValueError("The .env URL must specify the application role username")
    return role


def pg_connection(url: str, *, admin_user: str | None = None, admin_password: str | None = None):
    """Connect with the checkpoint schema as the SQL search_path.

    The Python PostgresSaver issues unqualified SQL table names. Setting the
    search_path on EVERY connection makes its data land in the dedicated schema.

    autocommit=True and dict_row are required for supported saver operations,
    particularly its one-time setup/migrations. Connection-string credentials
    are overridden only for interactive administrator setup.
    """
    kwargs: dict[str, Any] = {
        "autocommit": True,
        "row_factory": dict_row,
        "connect_timeout": 5,
        "options": f"-csearch_path={CHECKPOINT_SCHEMA}",
    }
    if admin_user is not None:
        kwargs["user"] = admin_user
        kwargs["password"] = admin_password
    return psycopg.connect(url, **kwargs)


def setup_schema(admin_user: str) -> None:
    """Create checkpoint objects through an administrator, then grant app DML.

    This command prompts securely for the local PostgreSQL administrator
    password. No administrator secret is written to .env or printed.

    It must be rerun by an administrator when package schema migrations change.
    The restricted application role intentionally cannot call saver.setup().
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    url = database_url()
    app_role = app_role_name(url)
    password = getpass.getpass(f"Password for PostgreSQL administrator '{admin_user}': ")
    if not password:
        raise ValueError("Administrator password must not be empty")

    with pg_connection(url, admin_user=admin_user, admin_password=password) as connection:
        # Fixed, quoted identifier: no user-provided SQL injected into a DDL name.
        connection.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}")
            .format(sql.Identifier(CHECKPOINT_SCHEMA))
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}")
            .format(sql.Identifier(CHECKPOINT_SCHEMA), sql.Identifier(app_role))
        )

        # Automatically creates/migrates checkpoints, checkpoint_blobs,
        # checkpoint_writes, checkpoint_migrations, etc. for installed package.
        saver = PostgresSaver(connection)
        saver.setup()

        # Grant table-specific DML, NOT CREATE, ALTER, DROP, or schema ownership.
        for table_name in CHECKPOINT_TABLES:
            connection.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {}.{} TO {}")
                .format(
                    sql.Identifier(CHECKPOINT_SCHEMA),
                    sql.Identifier(table_name),
                    sql.Identifier(app_role),
                )
            )
        print("[SETUP] Checkpoint schema and migrations installed by administrator")
        print(f"[SETUP] Restricted role '{app_role}' granted checkpoint table DML")
        print("[SETUP] No access to Lab 19 trip_preferences changed")


def open_runtime_graph():
    """Return a fresh restricted database connection and compiled workflow.

    Caller must close the returned connection. We deliberately do not run
    saver.setup() here because this connection is the least-privileged app role.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    connection = pg_connection(database_url())
    try:
        graph = build_graph(PostgresSaver(connection))
    except BaseException:
        connection.close()
        raise
    return connection, graph


def pause(thread_id: str, destination: str) -> None:
    """Start and checkpoint one execution. This Python process then exits."""
    conf = config_for(thread_id)
    conn, graph = open_runtime_graph()
    try:
        previous = graph.get_state(conf)
        if previous and previous.values:
            raise ValueError(
                f"Thread '{thread_id}' already has state. Choose a NEW thread ID to pause again."
            )

        initial: TravelState = {
            "destination": destination,
            "phase": "new",
            "approved": None,
        }
        result = graph.invoke(initial, config=conf)
        if "__interrupt__" not in result:
            raise AssertionError("Expected approval_gate to interrupt")
        saved = graph.get_state(conf)
        if not saved or saved.next != ("approval_gate",):
            raise AssertionError("Persisted checkpoint is not waiting at approval_gate")

        print("[PAUSED] Human approval required")
        print("[CHECKPOINT] Thread:", thread_id)
        print("[CHECKPOINT] Next:", saved.next)
        print("[CHECKPOINT] Phase:", saved.values["phase"])
        print("[EXIT] This command ends. Run status/resume in a NEW process.")
    finally:
        conn.close()


def status(thread_id: str) -> None:
    """Inspect an existing checkpoint without resuming or mutating the graph."""
    conf = config_for(thread_id)
    conn, graph = open_runtime_graph()
    try:
        saved = graph.get_state(conf)
        if not saved or not saved.values:
            raise ValueError(f"No checkpoint found for '{thread_id}'")
        print("[STATUS] Thread:", thread_id)
        print("[STATUS] Next:", saved.next)
        print("[STATUS] Phase:", saved.values.get("phase"))
        print("[STATUS] Destination:", saved.values.get("destination"))
        print("[STATUS] Finished:", not bool(saved.next))
    finally:
        conn.close()


def resume(thread_id: str, decision: bool) -> None:
    """Resume the SAME interrupted thread from persistent PostgreSQL state.

    This demo's CLI boolean represents a trusted human decision. A production
    API must derive approval and thread ownership from authenticated identity,
    enforce limits, and revalidate real-world conditions before side effects.
    """
    conf = config_for(thread_id)
    conn, graph = open_runtime_graph()
    try:
        before = graph.get_state(conf)
        if not before or before.next != ("approval_gate",):
            raise ValueError(
                "Thread must exist and be paused at approval_gate; cannot resume here"
            )
        result: TravelState = graph.invoke(Command(resume=decision), config=conf)
        after = graph.get_state(conf)
        if result["approved"] is not decision or (after and after.next):
            raise AssertionError("Graph did not complete with the supplied approval")
        print("[RESUMED] Thread:", thread_id)
        print("[RESUMED] Decision:", decision)
        print("[FINISHED] Phase:", result["phase"])
        print("[CONFIRMED] Workflow survived across independent Python processes")
    finally:
        conn.close()


def run_offline_tests() -> None:
    """Exercise graph semantics without needing the PostgreSQL server."""
    for approved, expected in [
        (True, "demo_approved_no_booking"),
        (False, "demo_rejected_no_booking"),
    ]:
        graph = build_graph(InMemorySaver())
        config = config_for("offline-approval")
        paused = graph.invoke(
            {"destination": "Paris", "phase": "new", "approved": None},
            config=config,
        )
        assert "__interrupt__" in paused
        assert graph.get_state(config).next == ("approval_gate",)
        final = graph.invoke(Command(resume=approved), config=config)
        assert final["phase"] == expected
        assert not graph.get_state(config).next
        print(f"[PASS] Offline graph pause/resume: approved={approved}")
    try:
        config_for("/unsafe-thread/")
    except ValueError:
        print("[PASS] Invalid thread ID rejected")
    else:
        raise AssertionError("Invalid thread ID accepted")
    print("LAB 25: ALL 3 OFFLINE TESTS PASSED")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab 25: durable PostgreSQL graph checkpoint")
    parser.add_argument("command", choices=["setup", "pause", "status", "resume", "test"])
    parser.add_argument("--thread", default="lab25-trip-001")
    parser.add_argument("--destination", default="Paris")
    parser.add_argument("--decision", choices=["approve", "reject"], default="approve")
    parser.add_argument("--admin-user", default="admin")
    args = parser.parse_args()

    try:
        if args.command == "setup":
            setup_schema(args.admin_user)
        elif args.command == "pause":
            pause(args.thread, args.destination)
        elif args.command == "status":
            status(args.thread)
        elif args.command == "resume":
            resume(args.thread, args.decision == "approve")
        else:
            run_offline_tests()
    except (psycopg.Error, ValueError, RuntimeError) as exc:
        # DB exception text can contain DSN parameters in rare cases; avoid
        # printing the full repr to prevent accidental credential exposure.
        if isinstance(exc, psycopg.Error):
            print("[DATABASE ERROR] PostgreSQL operation failed.")
            print("[DATABASE ERROR] SQLSTATE:", exc.sqlstate or "not provided")
            print("[HINT] Verify the role's password, checkpoint schema, and GRANTs.")
            print("[HINT] Run 'setup' as a database administrator once if needed.")
        else:
            print("[ERROR]", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
