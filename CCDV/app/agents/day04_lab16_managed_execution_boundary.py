"""AI Travel Buddy — Day 04, Lab 16: Private Tool Execution Boundary.

Certification objectives:
    CCDV-F: Distinguish managed agent control planes from tool execution.
    CCAR-F: Enforce access controls and minimize data crossing boundaries.

This standalone, offline lab simulates a tool worker that runs inside an
enterprise network. It does NOT connect to a private database, Anthropic API,
or a deployed Managed Agents sandbox.

Run from the AI Travel Buddy project root (file in app/agents/):
    uv run python -m app.agents.day02_lab16_managed_execution_boundary
"""

import json
from typing import Any


# A deliberately fictional database containing sensitive fields.
# Only a trusted worker should access complete records like these.
PRIVATE_BOOKINGS: dict[str, dict[str, str]] = {
    "TRV-1001": {
        "route": "Toulouse -> Paris",
        "booking_status": "confirmed",
        "customer_email": "traveler@example.com",
        "payment_token": "FAKE-PRIVATE-TOKEN",
    }
}


def query_private_database(booking_id: str) -> dict[str, str] | None:
    """Return a private booking record, or None when the ID is unknown.

    This is a local stand-in for a database operation. Never expose the
    entire result directly as an LLM-visible tool result.
    """
    return PRIVATE_BOOKINGS.get(booking_id)


def execute_booking_tool(
    booking_id: str,
    authorized_booking_ids: frozenset[str],
) -> dict[str, Any]:
    """Authorize a booking lookup and return a safe, limited response.

    Args:
        booking_id: Booking requested by the caller.
        authorized_booking_ids: Booking IDs this caller may read. In a real
            system, permissions must come from trusted authentication and
            authorization services, never model-generated arguments.

    Returns:
        A structured result with allowlisted fields or a safe error.
    """
    # PRE-EXECUTION GATE: reject unauthorized IDs before looking up data.
    if booking_id not in authorized_booking_ids:
        return {"status": "error", "error": "access_denied"}

    # PRIVATELY EXECUTED OPERATION: a database lookup, locally mocked here.
    private_record = query_private_database(booking_id)
    if private_record is None:
        return {"status": "error", "error": "booking_not_found"}

    # POST-EXECUTION OUTPUT GATE: use an explicit allowlist of safe fields.
    # customer_email and payment_token are intentionally not passed to Claude.
    safe_data = {
        "route": private_record["route"],
        "booking_status": private_record["booking_status"],
        "data_source": "mock_private_database",
    }
    return {"status": "success", "data": safe_data}


def run_lab() -> None:
    """Execute three checks for authorization and information minimization."""
    caller_permissions = frozenset({"TRV-1001"})

    print("\n--- TEST 1: AUTHORIZED LOOKUP ---")
    allowed = execute_booking_tool("TRV-1001", caller_permissions)
    print(json.dumps(allowed, indent=2))
    assert allowed["status"] == "success"
    assert allowed["data"]["route"] == "Toulouse -> Paris"
    assert allowed["data"]["booking_status"] == "confirmed"

    # Check that the agent-visible result contains none of the private values
    # or sensitive field names, even though the underlying record does.
    serialized_result = json.dumps(allowed)
    for forbidden in (
        "customer_email", "payment_token",
        "traveler@example.com", "FAKE-PRIVATE-TOKEN",
    ):
        assert forbidden not in serialized_result, f"Leaked: {forbidden}"
    print("[PASS] Only approved fields crossed the tool-result boundary.")

    print("\n--- TEST 2: UNAUTHORIZED EXISTING BOOKING ---")
    denied = execute_booking_tool("TRV-1001", frozenset())
    print(json.dumps(denied, indent=2))
    assert denied == {"status": "error", "error": "access_denied"}
    print("[PASS] Access denied before private lookup.")

    print("\n--- TEST 3: AUTHORIZED ID NOT FOUND ---")
    missing = execute_booking_tool("TRV-9999", frozenset({"TRV-9999"}))
    print(json.dumps(missing, indent=2))
    assert missing == {"status": "error", "error": "booking_not_found"}
    print("[PASS] Not-found and unauthorized cases stay distinct.")

    print("\nLAB 16: ALL TESTS PASSED (LOCAL SIMULATION ONLY)")


if __name__ == "__main__":
    run_lab()
