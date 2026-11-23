"""AI Travel Buddy — Day 05, Lab 23: LangGraph State, Nodes and Routing.

Certification coverage
----------------------
CCDV-F: Graph-based orchestration versus Claude Agent SDK's model-driven tools.
CCAR-F: Distinguish authoritative external memory from execution checkpoints.

What this lab demonstrates
--------------------------
1. TypedDict defines the graph's shared state schema.
2. Each node receives that state and returns only fields it updates.
3. `add_conditional_edges` selects the next node using Python logic.
4. `Annotated[..., operator.add]` appends audit events across nodes.
5. `InMemorySaver` checkpoints graph state per thread_id *within this process*.

This exercise uses fictional train and hotel recommendations and NO Claude API
calls, bookings or external search providers. It does not replace Claude Agent
SDK subagents (Lab 22); it demonstrates a different orchestration approach.

Run from the existing CCDV project root on Windows:
    uv add langgraph
    uv run python -m app.agents.day05_lab23_langgraph_state_routing test
    uv run python -m app.agents.day05_lab23_langgraph_state_routing demo

`test` uses fictional in-memory trip data and makes no database connection.
`demo` reads the existing demo trip from PostgreSQL via Lab 20's read-only loader.
It does not write to PostgreSQL. This lab has no paid API operations.
"""

from __future__ import annotations

import argparse
import operator
from decimal import Decimal
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


Service = Literal["train", "hotel"]


class TripFacts(TypedDict):
    """Authoritative trip attributes supplied to the graph by its caller.

    `user_id` is an exercise identifier, NOT an authentication mechanism.
    Production applications must derive identity from verified auth context.
    """

    user_id: str
    trip_id: str
    origin: str
    destination: str
    travelers: int
    budget_eur: str  # Decimal serialized exactly; no floating-point money.


class TripGraphState(TypedDict, total=False):
    """Shared graph state; nodes return partial updates to these fields.

    `audit_events` has a reducer: each node may return a new list of entries,
    and LangGraph combines them using list concatenation. Ordinary fields
    (e.g., `finding`) are overwritten when updated.
    """

    trip: TripFacts
    requested_service: Service
    finding: dict[str, str]
    summary: str
    completed: bool
    audit_events: Annotated[list[str], operator.add]


def validate_trip(state: TripGraphState) -> dict[str, object]:
    """Validate external facts and the requested route before doing research.

    In production, this state should come from authorized PostgreSQL access;
    treating text invented by the model as a trusted user identifier is unsafe.
    """
    trip = state["trip"]
    service = state["requested_service"]
    if service not in ("train", "hotel"):
        raise ValueError("requested_service must be 'train' or 'hotel'")
    if not trip["origin"].strip() or not trip["destination"].strip():
        raise ValueError("Origin and destination are required")
    if not (1 <= trip["travelers"] <= 12):
        raise ValueError("Traveler count must be between 1 and 12")
    if Decimal(trip["budget_eur"]) <= 0:
        raise ValueError("Budget must be positive")
    return {"audit_events": ["validate_trip:passed"]}


def select_research_node(state: TripGraphState) -> Service:
    """Make a deterministic routing choice; the LLM does NOT choose this edge.

    This is a routing function, not a graph node: its return value is an edge
    label, which `add_conditional_edges` maps to the next node.
    """
    return state["requested_service"]


def train_research(state: TripGraphState) -> dict[str, object]:
    """Return one fictional train option; never contact a real provider."""
    trip = state["trip"]
    return {
        "finding": {
            "kind": "train",
            "detail": f"Fictional demo train: {trip['origin']} → {trip['destination']}",
            "source": "mock-fixture",
        },
        "audit_events": ["train_research:complete"],
    }


def hotel_research(state: TripGraphState) -> dict[str, object]:
    """Return one fictional hotel option; never contact a real provider."""
    trip = state["trip"]
    return {
        "finding": {
            "kind": "hotel",
            "detail": f"Fictional demo hotel in {trip['destination']}",
            "source": "mock-fixture",
        },
        "audit_events": ["hotel_research:complete"],
    }


def summarize(state: TripGraphState) -> dict[str, object]:
    """Produce a report from the chosen branch's validated mock finding."""
    expected = state["requested_service"]
    finding = state.get("finding")
    if finding is None or finding.get("kind") != expected:
        raise ValueError("Missing or mismatched research result")
    trip = state["trip"]
    summary = (
        f"{finding['detail']}. Travelers: {trip['travelers']}; "
        f"saved trip budget: EUR {Decimal(trip['budget_eur']):.2f}. "
        "This is fictional demo data, not live availability or a booking."
    )
    return {
        "summary": summary,
        "completed": True,
        "audit_events": ["summarize:complete"],
    }


def build_graph():
    """Build a StateGraph with explicit nodes, edges and a RAM checkpointer.

    Unlike an Agent SDK manager, LangGraph routes requests by the graph edges
    we author. The checkpointer is keyed by a `thread_id` supplied at invoke.
    `InMemorySaver` does not survive process restart and is not a durable DB.
    """
    builder = StateGraph(TripGraphState)
    builder.add_node("validate", validate_trip)
    builder.add_node("train_research", train_research)
    builder.add_node("hotel_research", hotel_research)
    builder.add_node("summarize", summarize)

    builder.add_edge(START, "validate")
    builder.add_conditional_edges(
        "validate",
        select_research_node,
        {"train": "train_research", "hotel": "hotel_research"},
    )
    builder.add_edge("train_research", "summarize")
    builder.add_edge("hotel_research", "summarize")
    builder.add_edge("summarize", END)

    # Checkpoints record the graph's execution state, not authoritative trip
    # preferences. Lab 19's PostgreSQL table remains the source of truth.
    return builder.compile(checkpointer=InMemorySaver())


def fictional_trip() -> TripFacts:
    """Return deterministic, fictional input for tests without PostgreSQL."""
    return {
        "user_id": "demo-user-001",
        "trip_id": "demo-trip-001",
        "origin": "Toulouse",
        "destination": "Paris",
        "travelers": 4,
        "budget_eur": "300.00",
    }


def invoke_trip(graph, trip: TripFacts, service: Service, thread_id: str):
    """Execute one explicit branch with a per-run graph checkpoint ID.

    A production thread_id must be authorized and scoped to the authenticated
    caller. Do not reuse another user's thread identifier.
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {"trip": trip, "requested_service": service, "audit_events": []},
        config=config,
    )
    return result, config


def run_tests() -> None:
    """Exercise graph routing, reducers, checkpointing, and validation."""
    graph = build_graph()
    trip = fictional_trip()

    train_state, train_cfg = invoke_trip(graph, trip, "train", "lab23-test-train")
    assert train_state["finding"]["kind"] == "train"
    assert "hotel_research:complete" not in train_state["audit_events"]
    assert train_state["completed"] is True
    print("[PASS] Conditional edge routes train requests only to train node")

    hotel_state, hotel_cfg = invoke_trip(graph, trip, "hotel", "lab23-test-hotel")
    assert hotel_state["finding"]["kind"] == "hotel"
    assert "train_research:complete" not in hotel_state["audit_events"]
    assert hotel_state["completed"] is True
    print("[PASS] Conditional edge routes hotel requests only to hotel node")

    assert train_state["audit_events"] == [
        "validate_trip:passed", "train_research:complete", "summarize:complete"
    ]
    print("[PASS] Annotated reducer appends independent node audit updates")

    # The separate thread IDs maintain separate checkpoint snapshots within
    # the current process, with no cross-thread overwrite.
    saved_train = graph.get_state(train_cfg).values
    saved_hotel = graph.get_state(hotel_cfg).values
    assert saved_train["finding"]["kind"] == "train"
    assert saved_hotel["finding"]["kind"] == "hotel"
    assert saved_train["summary"] != saved_hotel["summary"]
    print("[PASS] Checkpointer isolates state by thread_id within this process")

    try:
        invalid = dict(trip)
        invalid["travelers"] = 0
        invoke_trip(graph, invalid, "train", "lab23-test-invalid")  # type: ignore[arg-type]
    except ValueError as exc:
        assert "Traveler count" in str(exc)
    else:
        raise AssertionError("Invalid traveler count should fail before research")
    print("[PASS] Invalid trip input rejected before research nodes execute")

    print("LAB 23: ALL 5 LANGGRAPH TESTS PASSED")


def run_demo() -> None:
    """Read authorized trip facts from Lab 20 and execute the graph locally.

    This is only a demo: fixed fictional user/trip IDs are NEVER appropriate
    for enforcing real multi-tenant user identity in a production service.
    """
    from app.agents.day05_lab20_context_pruning_compaction import (
        DEMO_TRIP_ID, DEMO_USER_ID, load_trusted_trip,
    )

    trusted = load_trusted_trip(DEMO_USER_ID, DEMO_TRIP_ID)
    trip: TripFacts = {
        "user_id": trusted.user_id,
        "trip_id": trusted.trip_id,
        "origin": trusted.origin,
        "destination": trusted.destination,
        "travelers": trusted.travelers,
        "budget_eur": str(trusted.budget_eur),
    }
    graph = build_graph()
    result, cfg = invoke_trip(graph, trip, "train", "lab23-demo-train")
    print("[DB] Loaded current, fictional trip facts from PostgreSQL")
    print("[GRAPH] Route: validate -> train_research -> summarize -> END")
    print("[SUMMARY]", result["summary"])
    print("[AUDIT]", " | ".join(result["audit_events"]))
    print("[CHECKPOINT]", graph.get_state(cfg).values["completed"])
    print("[NOTE] InMemorySaver is not durable across Python process restarts")


def main() -> None:
    """Dispatch small CLI commands without modifying prior lab modules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["test", "demo"])
    arguments = parser.parse_args()
    if arguments.command == "test":
        run_tests()
    else:
        run_demo()


if __name__ == "__main__":
    main()
