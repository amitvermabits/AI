
"""
AI Travel Buddy - Dependency Revalidation Lab.

Certification objectives:
    CCDV-F: Implement deterministic dependency checks.
    CCAR-F: Selectively revalidate affected subagent work.

This lab identifies tasks affected by changed inputs.
It does not execute agents or perform external API calls.

Run:
    uv run python -m app.agents.dependency_revalidation_lab
"""


# Each task declares which input facts it depends on.
TASK_DEPENDENCIES: dict[str, set[str]] = {
    "transport": {"travel_dates"},
    "sightseeing": {"hotel_location", "travel_dates"},
    "restaurants": {"dietary_preferences", "food_budget"},
}


def find_affected_tasks(
    changed_fields: set[str],
    dependencies: dict[str, set[str]],
) -> list[str]:
    """
    Find tasks that depend on any changed input.

    Args:
        changed_fields: Input facts that have changed.
        dependencies: Mapping of tasks to their required facts.

    Returns:
        Names of tasks requiring revalidation.
    """
    affected: list[str] = []

    for task_name, required_fields in dependencies.items():
        # Set intersection finds shared field names.
        if changed_fields.intersection(required_fields):
            affected.append(task_name)

    return affected


if __name__ == "__main__":
    # The recovered hotel has a different location.
    changed_fields = {"hotel_location"}

     # Test 2: Multiple input changes.
    # Identify every task affected by either change.
    changed_fields = {"travel_dates", "food_budget"}

    affected_tasks = find_affected_tasks(
        changed_fields,
        TASK_DEPENDENCIES,
    )

    print("Revalidate:", affected_tasks)
