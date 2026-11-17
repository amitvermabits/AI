
"""
AI Travel Buddy - Transport Search Tools.

Certification:
    CCDV-F | Domain 1 | Skill 1.1 - Agent Architecture

Purpose:
    Provide executable Python functions that an
    AI agent can invoke to search transport options.

Concepts:
    - Tool implementation
    - Tool inputs and outputs
    - Separation of LLM reasoning and Python execution

Current implementation:
    Uses MOCK transport prices for learning.

    No external transport API is called.
    These prices are NOT live fares.

Run from the project root:
    uv run python -m app.tools.transport
"""


def validate_route(
    from_city: str,
    to_city: str
) -> None:
    """
    Validate that the requested route is supported.

    Args:
        from_city: Departure city.
        to_city: Destination city.

    Raises:
        ValueError: If the route is not supported.

    Note:
        This lab supports only Toulouse to Paris.
    """

    if (
        from_city.strip().lower() != "toulouse"
        or to_city.strip().lower() != "paris"
    ):
        raise ValueError(
            "Mock data supports Toulouse to Paris only."
        )


def search_trains(
    from_city: str,
    to_city: str
) -> dict:
    """
    Search for train options using simulated data.

    Args:
        from_city: Departure city.
        to_city: Destination city.

    Returns:
        Dictionary with transport mode,
        route, sample price and currency.

    Note:
        A future implementation may call a
        real train booking/search API.
    """

    validate_route(from_city, to_city)

    return {
        "mode": "train",
        "from_city": from_city,
        "to_city": to_city,
        "price": 135,
        "currency": "EUR",
        "data_source": "mock"
    }


def search_buses(
    from_city: str,
    to_city: str
) -> dict:
    """
    Search for bus options using simulated data.

    Args:
        from_city: Departure city.
        to_city: Destination city.

    Returns:
        Dictionary with transport mode,
        route, sample price and currency.

    Note:
        A future implementation may call a
        real bus booking/search API.
    """

    validate_route(from_city, to_city)

    return {
        "mode": "bus",
        "from_city": from_city,
        "to_city": to_city,
        "price": 65,
        "currency": "EUR",
        "data_source": "mock"
    }


if __name__ == "__main__":
    # Local test without making any Claude API calls.
    print("Train:", search_trains("Toulouse", "Paris"))
    print("Bus:", search_buses("Toulouse", "Paris"))
