"""AI Travel Buddy - Day 04, Lab 17: Agent SDK tool lifecycle hooks.
deterministic hooks and (programmatic guardrails).
Objectives:
    CCDV-F: Register PreToolUse and PostToolUse SDK hooks.
    CCAR-F: Apply deterministic authorization before executing tools.

This is a local SDK demonstration using fictional bookings, not a deployed
Managed Agent or a production identity/access management implementation.

Run from the project root:
    uv run python -m app.agents.day04_lab17_sdk_hooks
"""

import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)

# In a real service, derive authorization from an authenticated identity,
# never from the model's request or prompt.
AUTHORIZED_BOOKINGS = frozenset({"TRV-1001"})
MOCK_PRIVATE_DB = {
    "TRV-1001": {
        "route": "Toulouse -> Paris",
        "booking_status": "confirmed",
        "customer_email": "demo@example.com",
    },
    "TRV-9009": {
        "route": "Paris -> Lyon",
        "booking_status": "confirmed",
        "customer_email": "restricted@example.com",
    },
}

# Demonstration counters let us prove whether the Python tool executed.
EXECUTED_TOOL_IDS: list[str] = []


@tool(
    "lookup_booking",
    "Look up a fictional booking by its booking_id. Never expose PII.",
    {"booking_id": str},
)
async def lookup_booking_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Return a filtered booking record, with defense-in-depth authorization."""
    booking_id = str(args.get("booking_id", ""))
    EXECUTED_TOOL_IDS.append(booking_id)
    print(f"[PYTHON TOOL EXECUTED] booking_id={booking_id}")

    # A runtime hook is not a substitute for authorization in the tool.
    if booking_id not in AUTHORIZED_BOOKINGS:
        return {
            "content": [{"type": "text", "text": "access_denied"}],
            "isError": True,
        }

    private_record = MOCK_PRIVATE_DB.get(booking_id)
    if private_record is None:
        return {
            "content": [{"type": "text", "text": "booking_not_found"}],
            "isError": True,
        }

    # Explicit allowlist: do not send customer_email back to the model.
    safe_result = {
        "booking_id": booking_id,
        "route": private_record["route"],
        "booking_status": private_record["booking_status"],
        "data_source": "mock_private_database",
    }
    return {"content": [{"type": "text", "text": json.dumps(safe_result)}]}


async def before_booking_tool(
    input_data: dict[str, Any], tool_use_id: str | None, context: Any
) -> dict[str, Any]:
    """Deny unauthorized booking lookups before the Python tool executes."""
    booking_id = input_data.get("tool_input", {}).get("booking_id")

    if booking_id not in AUTHORIZED_BOOKINGS:
        print(f"[PRE HOOK] DENY booking_id={booking_id}")
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Booking access not authorized.",
            }
        }

    print(f"[PRE HOOK] PASS booking_id={booking_id}")
    return {}  # No additional decision; normal tool permissions still apply.


async def after_booking_tool(
    input_data: dict[str, Any], tool_use_id: str | None, context: Any
) -> dict[str, Any]:
    """Audit a completed tool call without exposing its full result."""
    booking_id = input_data.get("tool_input", {}).get("booking_id")
    print(f"[POST HOOK] Completed tool call for booking_id={booking_id}")
    return {}


async def run_case(options: ClaudeAgentOptions, booking_id: str) -> None:
    """Create a fresh SDK session and exercise the hook for one booking ID."""
    print(f"\n--- TEST: {booking_id} ---")
    before = len(EXECUTED_TOOL_IDS)
    saw_tool_request = False

    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            f"Call lookup_booking exactly once with booking_id='{booking_id}'. "
            "Then explain the result. Never claim unauthorized data was retrieved."
        )

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        saw_tool_request = True
                        print("[CLAUDE REQUESTED]", block.name, block.input)
                    elif isinstance(block, TextBlock):
                        print("[CLAUDE]", block.text)
            elif isinstance(message, ResultMessage):
                print("[RESULT]", message.subtype, "turns=", message.num_turns)

    executed = EXECUTED_TOOL_IDS[before:]
    print("[CHECK] Python tool executions:", executed)
    if not saw_tool_request:
        raise AssertionError("Claude did not request a tool; test is inconclusive")
    if booking_id in AUTHORIZED_BOOKINGS:
        assert booking_id in executed, "Authorized tool call did not execute"
    else:
        assert booking_id not in executed, "Denied tool call executed!"


def build_options() -> ClaudeAgentOptions:
    """Configure the fictional booking tool and its SDK lifecycle hooks."""
    server = create_sdk_mcp_server(
        name="travel", version="1.0.0", tools=[lookup_booking_tool]
    )
    tool_name = "mcp__travel__lookup_booking"
    return ClaudeAgentOptions(
        model="claude-haiku-5-5",
        system_prompt=(
            "You are AI Travel Buddy. Use the booking tool when requested. "
            "Data is fictional and must be described as mock data. "
            "Do not invent results if a tool is denied."
        ),
        tools=[],
        mcp_servers={"travel": server},
        allowed_tools=[tool_name],
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher=tool_name,
                    hooks=[before_booking_tool],
                    # A broken security callback should block the call.
                    on_failure="block",
                )
            ],
            "PostToolUse": [
                HookMatcher(matcher=tool_name, hooks=[after_booking_tool])
            ],
        },
        setting_sources=[],
        permission_mode="dontAsk",
        max_turns=3,
        max_budget_usd=0.10,
    )


async def main() -> None:
    """Run an authorized and a denied lookup through two SDK sessions."""
    load_dotenv(override=True)
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    options = build_options()
    await run_case(options, "TRV-1001")
    await run_case(options, "TRV-9009")
    print("\nLAB 17: AUTHORIZATION AND HOOK CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
