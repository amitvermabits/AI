
"""
AI Travel Buddy - Subagent Handoff Validation.

Learning objectives:
    CCDV-F: Validate structured subagent results.
    CCAR-F: Enforce handoff contracts at orchestration boundaries.

This lab validates response structure and a basic budget rule.
It does not verify real hotel availability or prices.

Run:
    uv run python -m app.agents.handoff_validation_lab
"""

from typing import Any


REQUIRED_FIELDS = (
    "property_name",
    "total_price_eur",
    "availability_status",
    "source",
)


def validate_hotel_result(
    result: dict[str, Any],
    budget_eur: float,
) -> list[str]:
    """
    Check whether a hotel subagent's result is acceptable.

    Args:
        result: Structured output from the hotel subagent.
        budget_eur: Maximum permitted accommodation price.

    Returns:
        A list of validation errors.
        An empty list means these checks passed.
    """
    errors: list[str] = []

    # Check mandatory contract fields.
    for field in REQUIRED_FIELDS:
        if field not in result or result[field] is None or result[field] == "":
            errors.append(f"Missing required field: {field}")

    # Validate the price independently of the model.
    price = result.get("total_price_eur")

    if isinstance(price, bool) or not isinstance(price, (int, float)):
        errors.append("Price must be a number")
    elif price < 0:
        errors.append("Price cannot be negative")
    elif price > budget_eur:
        errors.append("Accommodation exceeds budget")

    
    # Validate the allowed availability states.
    allowed_statuses = {
        "available",
        "unavailable",
        "unknown",
    }

    status = result.get("availability_status")

    if status is not None and status not in allowed_statuses:
        errors.append(
            f"Invalid availability status: {status}"
        )

      # Mock data must never be treated as confirmed
    # real-world hotel availability.
    if (
        result.get("source") == "mock-provider"
        and result.get("availability_status") == "available"
    ):
        errors.append(
            "Availability not verified: mock provider"
        )

    return errors


if __name__ == "__main__":
    # Simulated output from the hotel subagent.
    hotel_result = {
        "property_name": "Paris Central Apartment",
        "total_price_eur": 360,
        "availability_status": "available",
    }

    hotel_result = {
    "property_name": "Paris Central Apartment",
    "total_price_eur": 360,
    "availability_status": "available",
    "source": "mock-provider",
    "availability_status": "available"
}

    validation_errors = validate_hotel_result(
        result=hotel_result,
        budget_eur=400,
    )

    print("Validation errors:", validation_errors)
