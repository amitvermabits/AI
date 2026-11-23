"""AI Travel Buddy — Day 05, Lab 22: SDK subagent lifecycle and workflow completion.

CCDV-F topics:
    AgentDefinition, ClaudeAgentOptions.agents, Agent tool delegation,
    SDK MCP tools, SubagentStart / SubagentStop hooks, Agent tool-result
    correlation, ResultMessage, subagent tool restrictions.
CCAR-F topics:
    Context isolation, lifecycle observability, reliable completion gates,
    least privilege, and deterministic business validation.

This module is intentionally standalone. It imports ONLY the established
Lab 20 PostgreSQL trip loader when running ``demo`` or ``live``; tests are
fully offline and deterministic. No previous lab file is modified.

COMMANDS (from the AI/CCDV project root):
    uv run python -m app.agents.day05_lab22_subagent_completion_signals test
    uv run python -m app.agents.day05_lab22_subagent_completion_signals demo
    uv run python -m app.agents.day05_lab22_subagent_completion_signals live

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




@dataclass(frozen=True, slots=True)
class AgentToolOutcome:
    """Observed result of ONE Agent tool call, indexed by its tool_use_id.

    The SDK's ToolResultBlock and PostToolUse hook may provide either a
    structured result with a status, or an ordinary report with no explicit
    ``status`` key. Absence of a status does NOT mean failure: the latter is
    typical of some foreground Agent tool results.
    """

    status: str | None
    is_error: bool
    has_payload: bool
    source: str

    @property
    def completed_foreground(self) -> bool:
        """Require a real, non-error result; explicitly reject async launches.

        Status is not universally present, so only recognized *negative*
        statuses fail. ``SubagentStop`` is a separate required observation.
        """
        known_success = {None, "completed", "success", "succeeded"}
        return (
            not self.is_error
            and self.has_payload
            and self.status in known_success
        )


@dataclass(slots=True)
class LiveEvidence:
    """Independent audit trail for SDK and application-level evidence.

    * ``agent_calls``: manager requested delegation, indexed by ToolUseBlock.id.
    * ``started`` / ``stopped``: SDK lifecycle hooks, indexed by agent_id.
    * ``agent_results``: Agent tool completion, correlated to request ID.
    * ``reports``: trusted Python MCP handler outputs (not LLM claims).
    * ``manager_*``: global query status and final text.

    A SubagentStop hook means execution stopped, NOT necessarily succeeded;
    require the Agent result and real tool execution too.
    """

    agent_calls: dict[str, str] = field(default_factory=dict)
    started: dict[str, str] = field(default_factory=dict)
    stopped: dict[str, str] = field(default_factory=dict)
    agent_results: dict[str, AgentToolOutcome] = field(default_factory=dict)
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_call_count: dict[str, int] = field(default_factory=dict)
    manager_status: str | None = None
    manager_is_error: bool = False
    manager_stop_reason: str | None = None
    manager_stop_hook_seen: bool = False
    final_text: str = ""
    last_manager_text: str = ""

    def note_agent_call(self, call_id: str, specialist: str) -> None:
        """Record explicit model delegation, without granting new privileges."""
        self.agent_calls[call_id] = specialist

    def note_started(self, agent_id: str, specialist: str) -> None:
        """Record a SubagentStart lifecycle event."""
        self.started[agent_id] = specialist

    def note_stopped(self, agent_id: str, specialist: str) -> None:
        """Record a SubagentStop lifecycle event, correlated by agent_id."""
        self.stopped[agent_id] = specialist

    def note_agent_result(self, tool_use_id: str, outcome: AgentToolOutcome) -> None:
        """Correlate an Agent tool result to its original delegation request.

        A PostToolUse event can arrive before a ToolResultBlock. If both are
        observed, keep the more explicit result (status, failure, or payload).
        Never overwrite an error with an apparent success.
        """
        # Hooks can fire before their matching ToolUseBlock is streamed.
        # Keep the result by its ID and associate it with the call later.
        previous = self.agent_results.get(tool_use_id)
        if previous is None:
            self.agent_results[tool_use_id] = outcome
        elif previous.is_error:
            return
        elif outcome.is_error:
            self.agent_results[tool_use_id] = outcome
        elif previous.status is None and outcome.status is not None:
            self.agent_results[tool_use_id] = outcome
        elif not previous.has_payload and outcome.has_payload:
            self.agent_results[tool_use_id] = outcome

    def record_tool(self, specialist: str, report: dict[str, Any], trip: TripBrief) -> None:
        """Record a validated, real Python MCP handler invocation."""
        validate_specialist_report(specialist, report, trip)
        self.reports[specialist] = dict(report)
        self.tool_call_count[specialist] = self.tool_call_count.get(specialist, 0) + 1


def _json_or_original(value: Any) -> Any:
    """Decode JSON only when a raw SDK tool-result string is valid JSON."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _find_explicit_status(value: Any) -> str | None:
    """Find a structured status field, not an incidental word in prose.

    E.g., the text 'not completed' must NOT be interpreted as completed.
    Recognize JSON content blocks and nested tool response objects.
    """
    value = _json_or_original(value)
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, str):
            return status.strip().lower()
        # Prioritize the typed tool response, if present.
        for key in ("tool_use_result", "content", "result", "data"):
            if key in value:
                found = _find_explicit_status(value[key])
                if found:
                    return found
    elif isinstance(value, list):
        for element in value:
            found = _find_explicit_status(element)
            if found:
                return found
    return None


def _has_payload(value: Any) -> bool:
    """Determine whether a nonempty result was actually supplied."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def classify_agent_result(
    payload: Any, *, is_error: bool, source: str
) -> AgentToolOutcome:
    """Convert SDK tool result metadata to a small audited record."""
    return AgentToolOutcome(
        status=_find_explicit_status(payload),
        is_error=is_error,
        has_payload=_has_payload(payload),
        source=source,
    )


def parse_final_json(text: str) -> dict[str, Any]:
    """Parse a consolidated manager result, rejecting progress-only prose."""
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ValueError("Manager response contains an unfinished code fence")
        value = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Manager has not produced valid final JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Manager final response must be a JSON object")
    return data


def lifecycle_issues(evidence: LiveEvidence) -> list[str]:
    """Enforce SDK lifecycle completion without depending on JSON reports.

    Matching by names alone is insufficient for repeated same-name subagents;
    this lab has one TRAIN and one HOTEL specialist, so type attribution is
    unambiguous. Start/stop are correlated by SDK agent_id, while results are
    correlated by Agent ToolUseBlock.id (tool_use_id).
    """
    required = {"train_specialist", "hotel_specialist"}
    problems: list[str] = []
    if evidence.manager_status != "success" or evidence.manager_is_error:
        problems.append(f"Overall ResultMessage was not successful: {evidence.manager_status!r}")

    for specialist in sorted(required):
        call_ids = [i for i, name in evidence.agent_calls.items() if name == specialist]
        if not call_ids:
            problems.append(f"{specialist}: no Agent ToolUseBlock delegation")
        starts = {i for i, name in evidence.started.items() if name == specialist}
        stops = {i for i, name in evidence.stopped.items() if name == specialist}
        if not starts:
            problems.append(f"{specialist}: missing SubagentStart hook")
        if not stops:
            problems.append(f"{specialist}: missing SubagentStop hook")
        unmatched = stops - starts
        if unmatched:
            problems.append(f"{specialist}: stop event has no matching start agent_id")
        if not (starts & stops):
            problems.append(f"{specialist}: no start/stop lifecycle pair")
        outcomes = [evidence.agent_results[cid] for cid in call_ids
                    if cid in evidence.agent_results]
        if not outcomes:
            problems.append(f"{specialist}: no correlated Agent tool result")
        elif not any(outcome.completed_foreground for outcome in outcomes):
            statuses = [outcome.status or "unclassified" for outcome in outcomes]
            problems.append(f"{specialist}: Agent result not completed: {statuses}")
    return problems


def workflow_issues(evidence: LiveEvidence, trip: TripBrief) -> list[str]:
    """Combine SDK lifecycle assurance with deterministic business checks.

    An SDK run can succeed while the user request remains incomplete.
    To pass, both Python MCP callbacks must execute AND the manager's final
    JSON must exactly match their validated reports.
    """
    issues = lifecycle_issues(evidence)
    required = {"train_specialist", "hotel_specialist"}
    for specialist in sorted(required):
        if evidence.tool_call_count.get(specialist, 0) != 1:
            issues.append(f"{specialist}: expected one successful MCP call")
        if specialist not in evidence.reports:
            issues.append(f"{specialist}: trusted MCP report missing")

    try:
        decoded = parse_final_json(evidence.final_text)
    except ValueError as exc:
        issues.append(str(exc))
        return issues

    if set(decoded) != {"train_specialist", "hotel_specialist", "disclaimer"}:
        issues.append("Final JSON must contain exactly both reports and a disclaimer")
    disclaimer = decoded.get("disclaimer")
    if not isinstance(disclaimer, str) or "fictional" not in disclaimer.lower():
        issues.append("Final JSON must explicitly label all values fictional")

    for specialist in sorted(required):
        report = decoded.get(specialist)
        if not isinstance(report, dict):
            issues.append(f"{specialist}: final JSON report missing")
            continue
        try:
            validate_specialist_report(specialist, report, trip)
        except (ValueError, ArithmeticError) as exc:
            issues.append(f"{specialist}: invalid report: {exc}")
            continue
        actual = evidence.reports.get(specialist)
        if actual is not None and report != actual:
            issues.append(f"{specialist}: final JSON differs from actual MCP result")
    return issues


def offline_fixture() -> TripBrief:
    """Safe fictional trip, requiring no real database or service."""
    return TripBrief("Toulouse", "Paris", 4, Decimal("300.00"))


def from_postgres() -> TripBrief:
    """Load the trusted Lab 20 PostgreSQL trip; never perform a write."""
    from app.agents.day05_lab20_context_pruning_compaction import load_trusted_trip

    trip = load_trusted_trip(DEMO_USER_ID, DEMO_TRIP_ID)
    return TripBrief(trip.origin, trip.destination, trip.travelers, trip.budget_eur)


def completed_fixture(trip: TripBrief) -> LiveEvidence:
    """Build a fully successful SYNTHETIC event trail for offline tests.

    Simulated hook events are NOT evidence that a real SDK integration works.
    They let us regression-test our verification logic deterministically.
    """
    evidence = LiveEvidence(manager_status="success", manager_stop_reason="end_turn")
    evidence.note_agent_call("tool-train", "train_specialist")
    evidence.note_agent_call("tool-hotel", "hotel_specialist")
    evidence.note_started("agent-train", "train_specialist")
    evidence.note_started("agent-hotel", "hotel_specialist")
    evidence.note_stopped("agent-train", "train_specialist")
    evidence.note_stopped("agent-hotel", "hotel_specialist")
    evidence.note_agent_result("tool-train", AgentToolOutcome("completed", False, True, "ToolResultBlock"))
    evidence.note_agent_result("tool-hotel", AgentToolOutcome(None, False, True, "PostToolUse"))
    train = asyncio.run(mock_train_search(trip))
    hotel = asyncio.run(mock_hotel_search(trip))
    evidence.record_tool("train_specialist", train, trip)
    evidence.record_tool("hotel_specialist", hotel, trip)
    evidence.final_text = json.dumps({
        "train_specialist": train,
        "hotel_specialist": hotel,
        "disclaimer": "All sample options are fictional, not real availability.",
    })
    return evidence


def run_tests() -> None:
    """Run fully offline regression checks for lifecycle and business gates."""
    trip = offline_fixture()
    train_task, hotel_task = build_delegations(trip)
    assert train_task.specialist == "train_specialist"
    assert hotel_task.specialist == "hotel_specialist"
    assert "300" not in train_task.instruction + hotel_task.instruction
    assert specialist_tool_sets() == {
        "train_specialist": (TRAIN_TOOL,),
        "hotel_specialist": (HOTEL_TOOL,),
    }
    print("[PASS] Minimal delegation context and separate tool permissions")

    local_reports = asyncio.run(run_local_fan_out(trip))
    for name, report in local_reports.items():
        validate_specialist_report(name, report, trip)
    print("[PASS] Read-only fictional operations return scoped reports")

    complete = completed_fixture(trip)
    assert lifecycle_issues(complete) == []
    assert workflow_issues(complete, trip) == []
    print("[PASS] Correlated start/stop hooks + Agent tool results + manager result")

    no_stop = completed_fixture(trip)
    no_stop.stopped.pop("agent-hotel")
    assert any("hotel_specialist: missing SubagentStop" in e for e in lifecycle_issues(no_stop))
    print("[PASS] Missing SubagentStop is NOT counted as completion")

    wrong_stop_id = completed_fixture(trip)
    wrong_stop_id.stopped.pop("agent-hotel")
    wrong_stop_id.note_stopped("agent-unmatched", "hotel_specialist")
    assert any("no start/stop lifecycle pair" in e for e in lifecycle_issues(wrong_stop_id))
    print("[PASS] Agent ID mismatch is rejected")

    no_tool_result = completed_fixture(trip)
    no_tool_result.agent_results.pop("tool-train")
    assert any("no correlated Agent tool result" in e for e in lifecycle_issues(no_tool_result))
    print("[PASS] Missing Agent ToolResult is NOT counted as completion")

    background = completed_fixture(trip)
    background.agent_results["tool-hotel"] = AgentToolOutcome("async_launched", False, True, "ToolResultBlock")
    assert any("not completed" in e for e in lifecycle_issues(background))
    print("[PASS] async_launched is not treated as foreground completion")

    error = completed_fixture(trip)
    error.agent_results["tool-train"] = AgentToolOutcome("failed", True, True, "ToolResultBlock")
    assert lifecycle_issues(error)
    print("[PASS] Failed or is_error Agent result is rejected")

    no_manager_finish = completed_fixture(trip)
    no_manager_finish.manager_status = "error_max_turns"
    assert lifecycle_issues(no_manager_finish)
    print("[PASS] Non-success ResultMessage is rejected")

    progress = completed_fixture(trip)
    progress.final_text = "I have started the two searches."
    assert any("final JSON" in e for e in workflow_issues(progress, trip))
    print("[PASS] Progress-only manager answer is rejected")

    altered = completed_fixture(trip)
    data = json.loads(altered.final_text)
    data["hotel_specialist"]["amount_eur"] = "999.00"
    altered.final_text = json.dumps(data)
    assert any("differs" in e for e in workflow_issues(altered, trip))
    print("[PASS] Fabricated manager report is rejected")

    reordered = LiveEvidence(manager_status="success")
    reordered.note_agent_result(
        "tool-late", AgentToolOutcome("completed", False, True, "PostToolUse")
    )
    reordered.note_agent_call("tool-late", "train_specialist")
    assert reordered.agent_results["tool-late"].completed_foreground
    print("[PASS] PostToolUse recorded before Agent ToolUseBlock remains correlated")

    assert _find_explicit_status("it is NOT completed") is None
    assert _find_explicit_status('{"status":"completed"}') == "completed"
    print("[PASS] Status parsing uses structured fields, not text guessing")
    print("LAB 22: ALL 13 OFFLINE TESTS PASSED")


def run_demo() -> None:
    """Read PostgreSQL, demonstrate fan-out; do not call any language model."""
    trip = from_postgres()
    tasks = build_delegations(trip)
    print("[POSTGRESQL]", f"{trip.origin} -> {trip.destination}; travelers={trip.travelers}; budget EUR {trip.budget_eur}")
    for task in tasks:
        print(f"[DELEGATION] {task.specialist}: {task.instruction}")
    reports = asyncio.run(run_local_fan_out(trip))
    for name, report in reports.items():
        validate_specialist_report(name, report, trip)
        print(f"[FICTIONAL {name}] {json.dumps(report, sort_keys=True)}")
    print("[PASS] Local parallel search demonstration; no Claude calls or bookings")


async def run_live() -> None:
    """Run REAL SDK manager and subagents with native completion signals.

    Verification requires:
    1. Manager Agent tool-use requests for both specialists.
    2. SubagentStart and SubagentStop with matching SDK agent_id.
    3. Foreground Agent tool results matched by tool_use_id.
    4. Actual MCP execution for each specialist.
    5. Global ResultMessage(subtype='success', is_error=False).
    6. Manager's final JSON equal to validated MCP reports.

    No real train/hotel provider is contacted. SDK calls are billable.
    """
    try:
        from claude_agent_sdk import (
            AgentDefinition, AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
            HookMatcher, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock,
            UserMessage, create_sdk_mcp_server, tool,
        )
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise RuntimeError("Missing SDK packages. Run: uv add claude-agent-sdk") from exc

    trip = from_postgres()
    train_task, hotel_task = build_delegations(trip)
    evidence = LiveEvidence()

    async def on_subagent_start(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """SDK emits the specialist identity and new agent_id at startup."""
        agent_id = str(input_data.get("agent_id", ""))
        agent_type = str(input_data.get("agent_type", ""))
        if agent_id and agent_type in specialist_tool_sets():
            evidence.note_started(agent_id, agent_type)
            print(f"[SubagentStart] {agent_type} agent_id={agent_id}")
        return {}

    async def on_subagent_stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """SDK stop hook is a lifecycle signal, not proof of task success."""
        agent_id = str(input_data.get("agent_id", ""))
        agent_type = str(input_data.get("agent_type", ""))
        if agent_id and agent_type in specialist_tool_sets():
            evidence.note_stopped(agent_id, agent_type)
            print(f"[SubagentStop] {agent_type} agent_id={agent_id}")
        return {}

    async def on_agent_tool_finish(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PostToolUse can deliver the Agent tool result before stream messages."""
        if input_data.get("tool_name") in ("Agent", "Task"):
            call_id = str(input_data.get("tool_use_id", tool_use_id or ""))
            payload = input_data.get("tool_response")
            outcome = classify_agent_result(payload, is_error=False, source="PostToolUse")
            evidence.note_agent_result(call_id, outcome)
            if call_id in evidence.agent_calls:
                name = evidence.agent_calls[call_id]
                print(f"[PostToolUse] {name} status={outcome.status or 'not supplied'}")
        return {}

    async def on_manager_stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Optional visibility into manager Stop hook; ResultMessage is terminal."""
        evidence.manager_stop_hook_seen = True
        print("[Stop] Manager stop hook received")
        return {}

    @tool(
        "search_trains", "Read-only FICTIONAL train fixture (not live availability).",
        {"origin": str, "destination": str, "travelers": int},
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    async def search_trains(args: dict[str, Any]) -> dict[str, Any]:
        """Reject incorrect parameters before returning fictional train data."""
        if (args.get("origin") != trip.origin or
                args.get("destination") != trip.destination or
                args.get("travelers") != trip.travelers):
            return {"content": [{"type": "text", "text": "DENIED: mismatched trip parameters"}], "isError": True}
        report = await mock_train_search(trip)
        evidence.record_tool("train_specialist", report, trip)
        print("[MCP EXECUTED] train_specialist -> search_trains")
        return {"content": [{"type": "text", "text": json.dumps(report)}]}

    @tool(
        "search_hotels", "Read-only FICTIONAL hotel fixture (not live availability).",
        {"destination": str, "travelers": int},
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    async def search_hotels(args: dict[str, Any]) -> dict[str, Any]:
        """Reject incorrect parameters before returning fictional hotel data."""
        if args.get("destination") != trip.destination or args.get("travelers") != trip.travelers:
            return {"content": [{"type": "text", "text": "DENIED: mismatched trip parameters"}], "isError": True}
        report = await mock_hotel_search(trip)
        evidence.record_tool("hotel_specialist", report, trip)
        print("[MCP EXECUTED] hotel_specialist -> search_hotels")
        return {"content": [{"type": "text", "text": json.dumps(report)}]}

    travel_server = create_sdk_mcp_server(
        name="travel", version="1.0.0", tools=[search_trains, search_hotels]
    )
    options = ClaudeAgentOptions(
        tools=["Agent"],
        allowed_tools=["Agent", TRAIN_TOOL, HOTEL_TOOL],
        disallowed_tools=["Bash", "Read", "Write", "Edit", "WebSearch", "WebFetch"],
        permission_mode="default",
        setting_sources=[],
        max_turns=5,
        max_budget_usd=0.75,
        mcp_servers={"travel": travel_server},
        agents={
            "train_specialist": AgentDefinition(
                description="Look up fictional train options using the train MCP tool only.",
                prompt=(
                    "You are a train specialist. Call mcp__travel__search_trains exactly "
                    "once using the supplied trip facts. Return the EXACT JSON report "
                    "from that tool. Do not invent prices, book anything, or use hotel tools."
                ),
                tools=[TRAIN_TOOL], mcpServers=["travel"], maxTurns=5,
                background=False,
            ),
            "hotel_specialist": AgentDefinition(
                description="Look up fictional hotel options using the hotel MCP tool only.",
                prompt=(
                    "You are a hotel specialist. Call mcp__travel__search_hotels exactly "
                    "once using the supplied trip facts. Return the EXACT JSON report "
                    "from that tool. Do not invent prices, book anything, or use train tools."
                ),
                tools=[HOTEL_TOOL], mcpServers=["travel"], maxTurns=5,
                background=False,
            ),
        },
        hooks={
            "SubagentStart": [HookMatcher(hooks=[on_subagent_start])],
            "SubagentStop": [HookMatcher(hooks=[on_subagent_stop])],
            "PostToolUse": [HookMatcher(matcher="Agent|Task", hooks=[on_agent_tool_finish])],
            "Stop": [HookMatcher(hooks=[on_manager_stop])],
        },
        system_prompt=(
            "You are AI Travel Buddy's manager in a FICTIONAL lab. Delegate "
            "train research to train_specialist and hotel research to "
            "hotel_specialist, preferably at the same time. They must finish "
            "in the foreground before you respond. No bookings. "
            "Final answer MUST be ONLY a JSON object with keys "
            "train_specialist, hotel_specialist and disclaimer. "
            "Do not alter values: include the exact returned tool JSON for each. "
            "The disclaimer must state that all data are fictional. "
            "Do not produce an interim progress message as final output."
        ),
    )
    manager_prompt = (
        "Perform BOTH fictional delegated searches and WAIT for both foreground "
        "Agent results before finalizing. No live travel searches or bookings.\n"
        f"train_specialist: {train_task.instruction}\n"
        f"hotel_specialist: {hotel_task.instruction}\n"
        f"Trusted budget: EUR {trip.budget_eur:.2f}; do not invent numbers."
    )

    def receive_agent_result(tool_id: str, payload: Any, is_error: bool, source: str) -> None:
        """Correlate an Agent tool-result event to its ToolUseBlock.id."""
        outcome = classify_agent_result(payload, is_error=is_error, source=source)
        evidence.note_agent_result(tool_id, outcome)
        if tool_id in evidence.agent_calls:
            name = evidence.agent_calls[tool_id]
            print(f"[Agent result] {name} via {source}: "
                  f"status={outcome.status or 'no explicit status'} "
                  f"is_error={outcome.is_error} payload={outcome.has_payload}")

    async def collect_manager_response(client: Any) -> None:
        """Consume SDK events to the ResultMessage boundary."""
        evidence.manager_status = None
        evidence.manager_is_error = False
        evidence.final_text = ""
        evidence.last_manager_text = ""
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                nested = bool(getattr(message, "parent_tool_use_id", None))
                if not nested:
                    reason = getattr(message, "stop_reason", None)
                    if reason:
                        evidence.manager_stop_reason = str(reason)
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name in ("Agent", "Task") and not nested:
                        specialist = str(block.input.get("subagent_type", ""))
                        evidence.note_agent_call(block.id, specialist)
                        print(f"[Agent delegation] {specialist} call_id={block.id}")
                    elif isinstance(block, TextBlock) and not nested:
                        text_value = block.text.strip()
                        if text_value:
                            evidence.last_manager_text = text_value
                            print("[Manager text]", text_value[:550])
            elif isinstance(message, UserMessage):
                blocks = message.content if isinstance(message.content, list) else []
                for block in blocks:
                    if isinstance(block, ToolResultBlock):
                        receive_agent_result(
                            block.tool_use_id,
                            block.content,
                            bool(getattr(block, "is_error", False)),
                            "ToolResultBlock",
                        )
                # Some SDK versions also expose the decoded result here.
                source_id = getattr(message, "parent_tool_use_id", None)
                structured = getattr(message, "tool_use_result", None)
                if source_id in evidence.agent_calls and structured is not None:
                    receive_agent_result(source_id, structured, False, "UserMessage.tool_use_result")
            elif isinstance(message, ResultMessage):
                evidence.manager_status = message.subtype
                evidence.manager_is_error = bool(message.is_error)
                evidence.final_text = message.result or evidence.last_manager_text
                print(f"[ResultMessage] subtype={message.subtype} is_error={message.is_error}")
                print(f"[Manager stop_reason] {evidence.manager_stop_reason or 'not exposed'}")
                errors = getattr(message, "errors", None)
                if errors:
                    print("[SDK errors]", errors)

    print("[LIVE] Real Agent SDK delegation with lifecycle hooks; FICTIONAL tools only")
    print("[LIVE] No booking; SDK calls are billable (max_budget_usd=0.75 per run)")
    async with ClaudeSDKClient(options=options) as client:
        await client.query(manager_prompt)
        await collect_manager_response(client)
        issues = workflow_issues(evidence, trip)
        if issues and not lifecycle_issues(evidence):
            # A single extra manager-only turn may finish consolidation after
            # the specialists have completed. Do not ask to run the tools again.
            print("[FOLLOW-UP] Specialist lifecycle passed; requesting final consolidation only")
            await client.query(
                "Both specialists have completed. Do NOT call Agent or any MCP tool "
                "again. Respond now with ONLY the exact two existing fictional "
                "tool reports as JSON and a fictional disclaimer."
            )
            await collect_manager_response(client)

    issues = workflow_issues(evidence, trip)
    print("\n--- COMPLETION EVIDENCE ---")
    for name in ("train_specialist", "hotel_specialist"):
        calls = [cid for cid, typ in evidence.agent_calls.items() if typ == name]
        started = {aid for aid, typ in evidence.started.items() if typ == name}
        stopped = {aid for aid, typ in evidence.stopped.items() if typ == name}
        successful_results = [cid for cid in calls if cid in evidence.agent_results
                              and evidence.agent_results[cid].completed_foreground]
        print(f"{name}: Agent calls={len(calls)}; started={len(started)}; "
              f"stopped={len(stopped)}; foreground results={len(successful_results)}; "
              f"MCP executions={evidence.tool_call_count.get(name, 0)}")
    print(f"Manager: ResultMessage={evidence.manager_status}; "
          f"stop_reason={evidence.manager_stop_reason or 'not exposed'}")

    if issues:
        print("[FAIL] Incomplete multi-agent workflow — no success claim")
        for issue in issues:
            print("  -", issue)
        raise SystemExit(2)

    combined = parse_final_json(evidence.final_text)
    print("\n--- VERIFIED FICTIONAL REPORTS ---")
    print("[TRAIN]", json.dumps(combined["train_specialist"], sort_keys=True))
    print("[HOTEL]", json.dumps(combined["hotel_specialist"], sort_keys=True))
    print("[DISCLAIMER]", combined["disclaimer"])
    print("[PASS] Two SubagentStop events, two completed Agent results, "
          "successful ResultMessage, and consistent final reports")


def main() -> None:
    """CLI entry: tests and demo are safe; live makes a billable Claude call."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["test", "demo", "live"])
    action = parser.parse_args().action
    if action == "test":
        run_tests()
    elif action == "demo":
        run_demo()
    else:
        asyncio.run(run_live())


if __name__ == "__main__":
    main()
