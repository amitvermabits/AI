
"""
AI Travel Buddy - Targeted Subagent Recovery Lab.

Certification objectives:
    CCDV-F: Use validated subagent results in Python.
    CCAR-F: Isolate failures during multi-agent orchestration.

This module identifies failed subagent outputs.
It does not invoke actual subagents or execute retries.

Run:
    uv run python -m app.agents.targeted_recovery_lab
"""

from app.agents.handoff_validation_lab import (
    validate_hotel_result,
)


def plan_recovery(
    validation_results: dict[str, list[str]],
) -> dict[str, list[str]]:
    """
    Identify which subagent outputs need recovery.

    Args:
        validation_results:
            Maps each subagent name to its validation errors.
            An empty error list indicates that the checks passed.

    Returns:
        A recovery plan with:
        - recover: Subagents whose output failed validation.
        - retain_provisionally: Outputs that passed validation.

    Important:
        Retained outputs may still need revalidation if
        a recovered result changes their assumptions.
    """
    recover: list[str] = []
    retain_provisionally: list[str] = []

    for agent_name, errors in validation_results.items():
        if errors:
            recover.append(agent_name)
        else:
            retain_provisionally.append(agent_name)

    return {
        "recover": recover,
        "retain_provisionally": retain_provisionally,
    }


if __name__ == "__main__":
    # Mock hotel result without verified availability.
    hotel_result = {
        "property_name": "Paris Central Apartment",
        "total_price_eur": 360,
        "availability_status": "available",
        "source": "mock-provider",
    }

    # Reuse the validator from our previous lab.
    hotel_errors = validate_hotel_result(
        result=hotel_result,
        budget_eur=400,
    )

    # Simulate validation outcomes from three subagents.
    validation_results = {
        "transport": [],
        "hotel": hotel_errors,
        "sightseeing": [],
    }

    recovery_plan = plan_recovery(validation_results)

    print("Recovery plan:", recovery_plan)
