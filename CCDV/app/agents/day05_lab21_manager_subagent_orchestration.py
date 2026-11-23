"""AI Travel Buddy — Day 05, Lab 21: Manager and specialist subagents.

CCDV-F topics:
    AgentDefinition, ClaudeAgentOptions.agents, Agent tool delegation,
    SDK MCP tools, subagent tool restrictions, read-only tool annotations.
CCAR-F topics:
    Context isolation, least privilege, concurrent independent work,
    boundaries between model coordination and deterministic validation.

This module is intentionally standalone. It imports ONLY the established
Lab 20 PostgreSQL trip loader when running ``demo`` or ``live``; tests are
fully offline and deterministic. No previous lab file is modified.

COMMANDS (from the AI/CCDV project root):
    uv run python -m app.agents.day05_lab21_manager_subagent_orchestration test
    uv run python -m app.agents.day05_lab21_manager_subagent_orchestration demo
    uv run python -m app.agents.day05_lab21_manager_subagent_orchestration live

``test`` runs offline without PostgreSQL or Claude.
``demo`` reads the existing fictional PostgreSQL trip, then demonstrates
        local independent concurrent tasks. NO Claude API calls.
``live`` calls Claude Agent SDK and may use API credits. Run it only when
        ready to test genuine model-driven delegation. No booking is made.

All sample train/hotel results below are FICTIONAL; they are NOT prices,
search results, availability, or travel recommendations.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal


DEMO_USER_ID = "demo-user-001"
DEMO_TRIP_ID = "demo-trip-001"
TRAIN_TOOL = "mcp__travel__search_trains"
HOTEL_TOOL = "mcp__travel__search_hotels"


@dataclass(frozen=True, slots=True)
class TripBrief:
    """Minimal immutable travel facts supplied to the manager.

    No database password, raw conversation history, or private user profile
    is included in the delegations. Production code should derive the trip
    identity from authenticated authorization, not a user-supplied ID.
    """

    origin: str
    destination: str
    travelers: int
    budget_eur: Decimal


@dataclass(frozen=True, slots=True)
class Delegation:
    """One assignment: specialist identity and task, NOT tool permissions.

    AgentDefinition.tools configures actual SDK tool access separately.
    """

    specialist: Literal["train_specialist", "hotel_specialist"]
    instruction: str


def build_delegations(trip: TripBrief) -> tuple[Delegation, Delegation]:
    """Give each specialist only the facts needed for its narrow task.

    In particular, budget allocation and booking decisions are kept with the
    manager: a specialist may search, but must not create reservations.
    This is context minimization; authorization still requires trusted tools.
    """
    if trip.travelers < 1 or trip.budget_eur <= 0:
        raise ValueError("Trip requires a positive budget and traveler count")
    if not trip.origin.strip() or not trip.destination.strip():
        raise ValueError("Trip route must have two nonempty cities")

    train = Delegation(
        specialist="train_specialist",
        instruction=(
            f"Find FICTIONAL train possibilities from {trip.origin} to "
            f"{trip.destination} for {trip.travelers} travelers using your "
            "read-only train tool. Report fictional candidates only. "
            "Do not book and do not assert live availability."
        ),
    )
    hotel = Delegation(
        specialist="hotel_specialist",
        instruction=(
            f"Find FICTIONAL hotel possibilities in {trip.destination} for "
            f"{trip.travelers} travelers using your read-only hotel tool. "
            "Report fictional candidates only. Do not book and do not "
            "assert live availability."
        ),
    )
    return train, hotel


def specialist_tool_sets() -> dict[str, tuple[str, ...]]:
    """Document the intended subagent tool inventory, not just auto-approval.

    ``AgentDefinition.tools`` controls a specialist's exposed tools.
    Top-level ``allowed_tools`` only grants auto-approval; it does not by
    itself remove other tools from the inventory.
    """
    return {
        "train_specialist": (TRAIN_TOOL,),
        "hotel_specialist": (HOTEL_TOOL,),
    }


async def mock_train_search(trip: TripBrief) -> dict[str, Any]:
    """A read-only fictional stand-in for a train provider; no network call."""
    return {
        "source": "fictional_lab_fixture",
        "kind": "train",
        "route": f"{trip.origin} -> {trip.destination}",
        "travelers": trip.travelers,
        "sample": "Demo train itinerary; not a real service",
        "amount_eur": "125.00",
        "live_availability": False,
    }


async def mock_hotel_search(trip: TripBrief) -> dict[str, Any]:
    """A read-only fictional stand-in for a hotel provider; no network call."""
    return {
        "source": "fictional_lab_fixture",
        "kind": "hotel",
        "destination": trip.destination,
        "travelers": trip.travelers,
        "sample": "Demo hotel stay; not a real property",
        "amount_eur": "140.00",
        "live_availability": False,
    }


async def run_local_fan_out(trip: TripBrief) -> dict[str, dict[str, Any]]:
    """Fan out two INDEPENDENT read-only mock operations concurrently.

    ``asyncio.gather`` illustrates deterministic application-managed fan-out.
    This is distinct from *model-driven* Claude Agent SDK orchestration,
    which is exercised only by the opt-in ``live`` command.
    """
    train, hotel = await asyncio.gather(
        mock_train_search(trip), mock_hotel_search(trip)
    )
    return {"train_specialist": train, "hotel_specialist": hotel}


def validate_specialist_report(
    name: str, report: dict[str, Any], trip: TripBrief
) -> None:
    """Validate bounded output before a manager uses specialist findings.

    A specialist's generated output is not an authorization decision. In a
    production tool, enforce tenant access, price provenance, schema, and
    currency checks in trusted code, and refresh prices before purchase.
    """
    expected_kind = "train" if name == "train_specialist" else "hotel"
    if name not in specialist_tool_sets():
        raise ValueError("Unexpected specialist")
    if report.get("kind") != expected_kind:
        raise ValueError("Specialist response kind does not match assignment")
    if report.get("source") != "fictional_lab_fixture":
        raise ValueError("Unexpected source for this offline lab")
    if report.get("travelers") != trip.travelers:
        raise ValueError("Response traveler count does not match authoritative trip")
    if report.get("live_availability") is not False:
        raise ValueError("Fictional results must not claim live availability")
    amount = Decimal(str(report.get("amount_eur", "")))
    if amount <= 0:
        raise ValueError("Amount must be positive")



@dataclass(slots=True)
class LiveEvidence:
    """Independent evidence from SDK events and actual MCP tool callbacks.

    A successful ResultMessage or two Agent requests alone cannot prove the
    business workflow succeeded.  We record *actual tool executions* in our
    own process and compare their reports with the manager's final response.
    """

    agent_calls: dict[str, str] = field(default_factory=dict)
    agent_result_status: dict[str, str] = field(default_factory=dict)
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_call_count: dict[str, int] = field(default_factory=dict)
    sdk_status: str | None = None
    sdk_is_error: bool = False
    final_text: str = ""

    def record_tool(self, specialist: str, report: dict[str, Any], trip: TripBrief) -> None:
        """Called from the real Python MCP handler, not from Claude's prose."""
        validate_specialist_report(specialist, report, trip)
        self.reports[specialist] = dict(report)
        self.tool_call_count[specialist] = self.tool_call_count.get(specialist, 0) + 1


def parse_final_json(text: str) -> dict[str, Any]:
    """Parse a manager JSON report; accept optional Markdown fencing only.

    Requiring a machine-readable contract lets the application reject
    progress-only text. Avoid guessing report values from prose.
    """
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ValueError("Final JSON code fence is incomplete")
        value = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Manager did not return a valid final JSON report") from exc
    if not isinstance(data, dict):
        raise ValueError("Manager result must be a JSON object")
    return data


def assess_live_outcome(evidence: LiveEvidence, trip: TripBrief) -> list[str]:
    """Fail closed unless we have proof of real tool work AND final reports.

    This deterministic check is distinct from the model's SDK run status.
    It prevents a friendly message such as 'searches started' being counted
    as a successful end-to-end booking-research workflow.
    """
    issues: list[str] = []
    if evidence.sdk_status != "success" or evidence.sdk_is_error:
        issues.append(f"SDK response not successful: {evidence.sdk_status!r}")

    required = {"train_specialist", "hotel_specialist"}
    delegations = set(evidence.agent_calls.values())
    missing_delegations = required - delegations
    if missing_delegations:
        issues.append("No observed Agent delegation: " + ", ".join(sorted(missing_delegations)))

    missing_tools = required - set(evidence.reports)
    if missing_tools:
        issues.append("No successful MCP execution: " + ", ".join(sorted(missing_tools)))

    for call_id, specialist in evidence.agent_calls.items():
        status = evidence.agent_result_status.get(call_id)
        if status in ("async_launched", "running") and specialist not in evidence.reports:
            issues.append(f"{specialist} was launched but not completed")
        elif status in ("failed", "error"):
            issues.append(f"{specialist} returned a failed Agent tool result")

    try:
        decoded = parse_final_json(evidence.final_text)
    except ValueError as exc:
        issues.append(str(exc))
        return issues

    if set(decoded) != {"train_specialist", "hotel_specialist", "disclaimer"}:
        issues.append("Final JSON must have train_specialist, hotel_specialist and disclaimer")
    disclaimer = decoded.get("disclaimer")
    if not isinstance(disclaimer, str) or "fictional" not in disclaimer.lower():
        issues.append("Missing explicit fictional-data disclaimer")

    for specialist in sorted(required):
        report = decoded.get(specialist)
        if not isinstance(report, dict):
            issues.append(f"Final report for {specialist} is missing or invalid")
            continue
        try:
            validate_specialist_report(specialist, report, trip)
        except (ValueError, ArithmeticError) as exc:
            issues.append(f"Invalid {specialist} final report: {exc}")
            continue
        source_report = evidence.reports.get(specialist)
        if source_report is not None and report != source_report:
            issues.append(f"{specialist} final JSON differs from the actual MCP tool result")
    return issues


def extract_status(value: Any) -> str | None:
    """Best-effort observation of SDK tool result statuses; never authorization.

    The CLI may place a structured payload in tool_use_result, or encode it
    in a ToolResultBlock's text. We record this only for human diagnostics:
    the definitive proof remains the in-process MCP callback.
    """
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, str):
            return status
        for sub in value.values():
            found = extract_status(sub)
            if found:
                return found
    elif isinstance(value, list):
        for sub in value:
            found = extract_status(sub)
            if found:
                return found
    elif isinstance(value, str):
        for flag in ("async_launched", "completed", "failed"):
            if flag in value:
                return flag
    return None


def test_live_gate() -> None:
    """Offline regression tests for progress-only responses and mismatches."""
    trip = offline_fixture()
    evidence = LiveEvidence(
        agent_calls={"agent-a": "train_specialist", "agent-b": "hotel_specialist"},
        sdk_status="success",
        final_text="I started both searches at the same time.",
    )
    assert assess_live_outcome(evidence, trip)
    print("[PASS] SDK success + progress message is NOT workflow completion")

    train = asyncio.run(mock_train_search(trip))
    hotel = asyncio.run(mock_hotel_search(trip))
    evidence.record_tool("train_specialist", train, trip)
    evidence.record_tool("hotel_specialist", hotel, trip)
    evidence.agent_result_status = {"agent-a": "completed", "agent-b": "completed"}
    evidence.final_text = json.dumps({
        "train_specialist": train,
        "hotel_specialist": hotel,
        "disclaimer": "All samples are fictional and not real offers.",
    })
    assert not assess_live_outcome(evidence, trip)
    print("[PASS] Actual MCP results + matching final JSON complete workflow")

    bad = json.loads(evidence.final_text)
    bad["hotel_specialist"]["travelers"] = 9
    evidence.final_text = json.dumps(bad)
    assert assess_live_outcome(evidence, trip)
    print("[PASS] Manager cannot report contradictory specialist results")

    evidence.final_text = json.dumps({
        "train_specialist": train, "hotel_specialist": hotel,
        "disclaimer": "Fictional demo only",
    })
    evidence.agent_result_status["agent-b"] = "async_launched"
    # A background-launch marker alone is not failure if real tool execution
    # and final validated reports are already available.
    assert not assess_live_outcome(evidence, trip)
    print("[PASS] Background-launch marker does not override completed evidence")


def from_postgres() -> TripBrief:
    """Load the existing Lab 20 trusted trip snapshot; database READ only."""
    from app.agents.day05_lab20_context_pruning_compaction import load_trusted_trip

    trip = load_trusted_trip(DEMO_USER_ID, DEMO_TRIP_ID)
    return TripBrief(
        origin=trip.origin,
        destination=trip.destination,
        travelers=trip.travelers,
        budget_eur=trip.budget_eur,
    )


def offline_fixture() -> TripBrief:
    """Return the same imaginary trip without requiring a database server."""
    return TripBrief("Toulouse", "Paris", 4, Decimal("300.00"))


def run_tests() -> None:
    """Test contracts with no SDK import, external traffic, or DB access."""
    trip = offline_fixture()
    train, hotel = build_delegations(trip)

    assert train.specialist == "train_specialist"
    assert hotel.specialist == "hotel_specialist"
    assert "Toulouse" in train.instruction and "Paris" in hotel.instruction
    assert "300" not in train.instruction and "300" not in hotel.instruction
    print("[PASS] Minimal task context sent to independent specialists")

    tool_sets = specialist_tool_sets()
    assert TRAIN_TOOL in tool_sets["train_specialist"]
    assert HOTEL_TOOL not in tool_sets["train_specialist"]
    assert HOTEL_TOOL in tool_sets["hotel_specialist"]
    assert TRAIN_TOOL not in tool_sets["hotel_specialist"]
    assert all("book" not in tool for items in tool_sets.values() for tool in items)
    print("[PASS] Specialist tool inventories are distinct and read-only")

    reports = asyncio.run(run_local_fan_out(trip))
    assert set(reports) == set(tool_sets)
    for name, report in reports.items():
        validate_specialist_report(name, report, trip)
    print("[PASS] Independent mock tool tasks fan out and return valid reports")

    bad = dict(reports["hotel_specialist"], travelers=9)
    try:
        validate_specialist_report("hotel_specialist", bad, trip)
    except ValueError as exc:
        assert "traveler" in str(exc)
    else:
        raise AssertionError("Failed to reject conflicting specialist output")
    print("[PASS] Manager validation rejects contradictory specialist results")
    test_live_gate()
    print("LAB 21: ALL 8 OFFLINE TESTS PASSED")


def run_demo() -> None:
    """Exercise read-only PostgreSQL grounding plus offline fan-out."""
    trip = from_postgres()
    tasks = build_delegations(trip)
    print("--- POSTGRESQL GROUNDED MANAGER STATE ---")
    print(f"Route: {trip.origin} -> {trip.destination}")
    print(f"Travelers: {trip.travelers}; budget: EUR {trip.budget_eur:.2f}")
    for task in tasks:
        print(f"[DELEGATE] {task.specialist}: {task.instruction}")
    reports = asyncio.run(run_local_fan_out(trip))
    for name, report in reports.items():
        validate_specialist_report(name, report, trip)
        print(f"[REPORT] {name}: {json.dumps(report, sort_keys=True)}")
    print("[PASS] PostgreSQL-backed local fan-out completed")
    print("[INFO] No Claude API, actual provider search, or booking was used")


async def run_live() -> None:
    """Execute genuine Claude SDK delegation with independent completion checks.

    KEY LESSON: ResultMessage(subtype="success") means the SDK turn ended;
    it does NOT prove the train and hotel searches finished. We inspect
    actual Agent tool calls and collect the real Python MCP function outputs.
    A bounded second manager turn is allowed if the first only reports progress.

    This is still a synthetic lab. No real travel search or booking occurs.
    """
    try:
        from claude_agent_sdk import (
            AgentDefinition,
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
            ToolAnnotations,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
            create_sdk_mcp_server,
            tool,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Claude Agent SDK not installed. Run: uv add claude-agent-sdk"
        ) from exc

    trip = from_postgres()
    train_task, hotel_task = build_delegations(trip)
    evidence = LiveEvidence()

    @tool(
        "search_trains",
        "Read-only FICTIONAL train data fixture; not real prices or availability.",
        {"origin": str, "destination": str, "travelers": int},
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    async def search_trains(args: dict[str, Any]) -> dict[str, Any]:
        """Validate the requested trip and record the actual Python tool call."""
        if (
            args.get("origin") != trip.origin
            or args.get("destination") != trip.destination
            or args.get("travelers") != trip.travelers
        ):
            return {
                "content": [{"type": "text", "text": "DEMO_DENIED: invalid train parameters"}],
                "isError": True,
            }
        report = await mock_train_search(trip)
        evidence.record_tool("train_specialist", report, trip)
        print("[MCP EXECUTED] train_specialist -> search_trains")
        return {"content": [{"type": "text", "text": json.dumps(report)}]}

    @tool(
        "search_hotels",
        "Read-only FICTIONAL hotel data fixture; not real prices or availability.",
        {"destination": str, "travelers": int},
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    async def search_hotels(args: dict[str, Any]) -> dict[str, Any]:
        """Validate trip scope and record the actual Python tool call."""
        if args.get("destination") != trip.destination or args.get("travelers") != trip.travelers:
            return {
                "content": [{"type": "text", "text": "DEMO_DENIED: invalid hotel parameters"}],
                "isError": True,
            }
        report = await mock_hotel_search(trip)
        evidence.record_tool("hotel_specialist", report, trip)
        print("[MCP EXECUTED] hotel_specialist -> search_hotels")
        return {"content": [{"type": "text", "text": json.dumps(report)}]}

    travel_server = create_sdk_mcp_server(
        name="travel", version="1.0.0", tools=[search_trains, search_hotels]
    )

    # Tools exposed to the manager: only the Agent delegation tool.
    # Each specialist's own AgentDefinition.tools configures its inventory.
    # Root allowed_tools controls auto-approval, NOT available-tool scope.
    options = ClaudeAgentOptions(
        tools=["Agent"],
        mcp_servers={"travel": travel_server},
        allowed_tools=["Agent", TRAIN_TOOL, HOTEL_TOOL],
        disallowed_tools=["Bash", "Read", "Write", "Edit", "WebSearch", "WebFetch"],
        permission_mode="default",
        setting_sources=[],
        max_turns=24,
        max_budget_usd=0.75,
        agents={
            "train_specialist": AgentDefinition(
                description="Find fictional train candidates using only the train tool.",
                prompt=(
                    "You are the train specialist. Call mcp__travel__search_trains "
                    "once, with the exact trip parameters in the delegated task. "
                    "Return the tool's complete JSON as your report. "
                    "Do not call hotel tools, book, or claim real availability."
                ),
                tools=[TRAIN_TOOL],
                mcpServers=["travel"],
                maxTurns=5,
                background=False,  # Prefer waiting for a report, not async launch.
            ),
            "hotel_specialist": AgentDefinition(
                description="Find fictional hotel candidates using only the hotel tool.",
                prompt=(
                    "You are the hotel specialist. Call mcp__travel__search_hotels "
                    "once, with the exact trip parameters in the delegated task. "
                    "Return the tool's complete JSON as your report. "
                    "Do not call train tools, book, or claim real availability."
                ),
                tools=[HOTEL_TOOL],
                mcpServers=["travel"],
                maxTurns=5,
                background=False,
            ),
        },
        system_prompt=(
            "You manage the AI Travel Buddy synthetic lab. Use the Agent tool "
            "to delegate train research to train_specialist and hotel research "
            "to hotel_specialist. These independent tasks can run in parallel, "
            "but WAIT until both return completed results; DO NOT return a "
            "progress-only message. Never invent or modify tool values. "
            "Final output MUST be a bare JSON object with EXACTLY these keys: "
            "train_specialist, hotel_specialist, disclaimer. Each specialist "
            "value must be the COMPLETE JSON object reported by its own tool "
            "including source, kind, route/destination, travelers, sample, "
            "amount_eur, and live_availability. The disclaimer must explicitly "
            "say that the values are fictional. No Markdown fences or prose."
        ),
    )
    manager_prompt = (
        "Complete this synthetic orchestration task. Do not book anything. "
        "Call BOTH named Agent subagents, preferably concurrently and in the "
        "foreground, and WAIT for their reports before producing final JSON.\n"
        f"train_specialist: {train_task.instruction}\n"
        f"hotel_specialist: {hotel_task.instruction}\n"
        f"Trusted trip budget: EUR {trip.budget_eur:.2f}. "
        "Do not imply that mock fares or hotels are real. "
        "Your final reply must contain BOTH complete reports as exact JSON."
    )

    def observe_agent_result(tool_id: str, payload: Any) -> None:
        """Best-effort status logging for an Agent's SDK tool-result block."""
        if tool_id not in evidence.agent_calls:
            return
        status = extract_status(payload)
        if status:
            evidence.agent_result_status[tool_id] = status
        print(
            f"[AGENT RESULT] {evidence.agent_calls[tool_id]} "
            f"status={status or 'received (unclassified)'}"
        )

    async def collect_one_response(client: Any) -> None:
        """Consume one SDK response, including model calls and tool results."""
        evidence.sdk_status = None
        evidence.sdk_is_error = False
        evidence.final_text = ""
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                is_nested = bool(getattr(message, "parent_tool_use_id", None))
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name in ("Agent", "Task"):
                        specialist = str(block.input.get("subagent_type", "unknown"))
                        if not is_nested:
                            evidence.agent_calls[block.id] = specialist
                            print(f"[AGENT CALL] {specialist} (tool id: {block.id})")
                    elif isinstance(block, ToolUseBlock) and is_nested:
                        print(f"[SUBAGENT TOOL CALL] {block.name}")
                    elif isinstance(block, TextBlock) and not is_nested:
                        text = block.text.strip()
                        if text:
                            # Progress may be useful, but never marks workflow success.
                            print("[ASSISTANT]", text[:900])
            elif isinstance(message, UserMessage):
                for block in message.content if isinstance(message.content, list) else []:
                    if isinstance(block, ToolResultBlock):
                        observe_agent_result(block.tool_use_id, block.content)
                # SDK versions can attach structured metadata separately.
                if getattr(message, "parent_tool_use_id", None):
                    observe_agent_result(
                        message.parent_tool_use_id,
                        getattr(message, "tool_use_result", None),
                    )
            elif isinstance(message, ResultMessage):
                evidence.sdk_status = message.subtype
                evidence.sdk_is_error = bool(message.is_error)
                evidence.final_text = message.result or evidence.final_text
                print(f"[SDK] Run status: {message.subtype}; is_error={message.is_error}")
                if message.errors:
                    print("[SDK] Errors:", "; ".join(message.errors))

    print("[LIVE] Claude SDK orchestration — fictional data, no bookings")
    print("[LIVE] API usage is billable; run has USD 0.75 budget limit")
    async with ClaudeSDKClient(options=options) as client:
        for attempt in (1, 2):
            await client.query(manager_prompt if attempt == 1 else (
                "The prior answer did not satisfy the program's verified "
                "workflow requirements. Complete any missing named subagent "
                "research with foreground Agent calls and WAIT for the tools "
                "to finish; then return ONLY the exact JSON output of both "
                "search tools with a fictional-data disclaimer. If both tools "
                "have completed, do NOT rerun them: just emit their actual "
                "complete JSON reports. No progress updates as final output."
            ))
            await collect_one_response(client)
            issues = assess_live_outcome(evidence, trip)
            if not issues:
                break
            print(f"[INCOMPLETE] SDK turn {attempt}: " + "; ".join(issues))
            if evidence.sdk_is_error or evidence.sdk_status != "success":
                break  # No retries on SDK errors or exhausted budget.
            if attempt == 1:
                print("[RETRY] One bounded follow-up in the same SDK session")

    issues = assess_live_outcome(evidence, trip)
    print("[SDK] Distinct named Agent delegations:", sorted(set(evidence.agent_calls.values())))
    print("[SDK] Successful Python MCP handlers:", sorted(evidence.reports))
    if issues:
        print("[FAIL] Lab 21 business workflow incomplete")
        for item in issues:
            print("  -", item)
        print("[INFO] SDK success means a model turn finished, not a completed task.")
        raise SystemExit(2)

    verified = parse_final_json(evidence.final_text)
    print("--- VERIFIED FINAL REPORTS (FICTIONAL) ---")
    print("[TRAIN]", json.dumps(verified["train_specialist"], sort_keys=True))
    print("[HOTEL]", json.dumps(verified["hotel_specialist"], sort_keys=True))
    print("[DISCLAIMER]", verified["disclaimer"])
    print("[PASS] Both Agent delegations observed, both Python tools executed, and")
    print("       manager reports match validated MCP results; no booking occurred")


def main() -> None:
    """CLI: keep tests safe and live API execution explicitly opt-in."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["test", "demo", "live"])
    args = parser.parse_args()
    if args.action == "test":
        run_tests()
    elif args.action == "demo":
        run_demo()
    else:
        asyncio.run(run_live())


if __name__ == "__main__":
    main()
