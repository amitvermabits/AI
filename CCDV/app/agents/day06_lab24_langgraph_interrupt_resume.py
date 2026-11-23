"""Day 06 / Lab 24 — LangGraph human approval and resume.

Learning goals:
1. Understand what ``interrupt()`` actually does inside a graph node.
2. See why ``thread_id`` links the paused and resumed graph invocations.
3. Understand the difference between temporary InMemorySaver checkpoints and
   durable PostgreSQL checkpoints.

All travel data is fictional. No Claude API call or booking is performed.
Run:
    uv run python -m app.agents.day06_lab24_langgraph_interrupt_resume demo
    uv run python -m app.agents.day06_lab24_langgraph_interrupt_resume reject
    uv run python -m app.agents.day06_lab24_langgraph_interrupt_resume test
"""

from __future__ import annotations

import sys
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class TravelState(TypedDict):
    """Shared state passed between graph nodes."""

    destination: str
    phase: str
    approved: bool | None


def prepare(state: TravelState) -> dict[str, str]:
    """Prepare the fictional plan; does not perform booking actions."""
    return {"phase": "ready_for_approval"}


def approval_gate(state: TravelState) -> dict[str, str | bool]:
    """Pause and request human input before any simulated next stage.

    On resume, LangGraph re-enters this node and ``interrupt`` returns the
    value supplied using ``Command(resume=...)``. Keep everything before the
    interrupt side-effect free: it can run more than once.
    """
    human_decision = interrupt({
        "question": "Approve the FICTIONAL travel plan?",
        "destination": state["destination"],
    })
    if not isinstance(human_decision, bool):
        raise ValueError("Approval must be a boolean, True or False")
    return {
        "approved": human_decision,
        "phase": "approved" if human_decision else "rejected",
    }


def finish(state: TravelState) -> dict[str, str]:
    """Record final simulated outcome; never contact a booking provider."""
    if state["approved"] is True:
        return {"phase": "demo_approved_no_booking"}
    return {"phase": "demo_rejected"}


def build_graph():
    """Compile graph with in-process checkpoint persistence."""
    builder = StateGraph(TravelState)
    builder.add_node("prepare", prepare)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("finish", finish)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "approval_gate")
    builder.add_edge("approval_gate", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=InMemorySaver())


def run_once(approved: bool, *, verbose: bool = True) -> TravelState:
    """Demonstrate pause, checkpoint inspection and same-thread resume."""
    graph = build_graph()
    config = {"configurable": {"thread_id": "fictional-travel-001"}}
    initial: TravelState = {
        "destination": "Paris",
        "phase": "new",
        "approved": None,
    }

    # First invocation stops at interrupt() and yields an interrupt event.
    paused = graph.invoke(initial, config=config)
    assert "__interrupt__" in paused, "Expected graph to pause for approval"
    checkpoint = graph.get_state(config)
    assert checkpoint.next == ("approval_gate",), checkpoint.next
    if verbose:
        print("[PAUSED] Human approval required")
        print("[CHECKPOINT] Next node:", checkpoint.next)
        print("[CHECKPOINT] Phase:", checkpoint.values["phase"])

    # Resume using the SAME thread_id. This continues the interrupted node.
    resumed = graph.invoke(Command(resume=approved), config=config)
    assert resumed["approved"] is approved
    assert resumed["phase"] in ("demo_approved_no_booking", "demo_rejected")
    assert not graph.get_state(config).next, "Graph should be finished"
    if verbose:
        print("[RESUMED] Human decision:", approved)
        print("[FINISHED] Final phase:", resumed["phase"])
        print("[NOTE] InMemorySaver cannot resume after the Python process exits")
    return resumed


def run_tests() -> None:
    """Test both explicit human decisions without external APIs."""
    assert run_once(True, verbose=False)["phase"] == "demo_approved_no_booking"
    print("[PASS] Approval resumes the paused graph without booking")
    assert run_once(False, verbose=False)["phase"] == "demo_rejected"
    print("[PASS] Rejection resumes the paused graph safely")
    print("LAB 24: ALL 2 OFFLINE TESTS PASSED")


if __name__ == "__main__":
    mode: Literal["demo", "reject", "test"] = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if mode == "demo":
        run_once(True)
    elif mode == "reject":
        run_once(False)
    elif mode == "test":
        run_tests()
    else:
        raise SystemExit("Choose demo, reject, or test")
