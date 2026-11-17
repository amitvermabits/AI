
"""
AI Travel Buddy - Claude Tool Selection Lab.

Certification:
    CCDV-F | Domain 1 | Skill 1.1 - Agent Architecture

Learning objectives:
    1. Define tools using JSON input schemas.
    2. Allow Claude to select a tool.
    3. Inspect the structured tool_use response.
    4. Understand stop_reason and token usage.

Important:
    This exercise demonstrates tool SELECTION only.
    Python tools are not executed in this lesson.

Run from the project root:
    uv run python -m app.agents.tool_selection_lab
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv


def get_tool_definitions() -> list[dict]:
    """
    Define the tools available to Claude.

    A tool definition contains:
        name: Unique identifier for the tool.
        description: Helps Claude decide when to use it.
        input_schema: Defines the expected arguments.

    Returns:
        List of tool definitions for the Messages API.

    Note:
        These are declarations, not executable functions.
    """

    # Both tools require origin and destination cities.
    city_schema = {
        "type": "object",
        "properties": {
            "from_city": {
                "type": "string",
                "description": "Departure city"
            },
            "to_city": {
                "type": "string",
                "description": "Destination city"
            }
        },
        "required": ["from_city", "to_city"],
        "additionalProperties": False
    }

    return [
        {
            "name": "search_trains",
            "description": (
                "Search for train transport options "
                "between two cities."
            ),
            "input_schema": city_schema
        },
        {
            "name": "search_buses",
            "description": (
                "Search for bus transport options "
                "between two cities."
            ),
            "input_schema": city_schema
        }
    ]


def main() -> None:
    """
    Request Claude's initial tool decision.

    Process:
        1. Load environment configuration.
        2. Initialize the Anthropic API client.
        3. Send the user goal and tool definitions.
        4. Inspect the response without executing tools.

    Raises:
        RuntimeError: If the API key is missing.
        Anthropic SDK errors: If the API request fails.
    """

    # Load ANTHROPIC_API_KEY and CLAUDE_MODEL.
    load_dotenv(override=True)

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing from .env"
        )

    model = os.getenv(
        "CLAUDE_MODEL",
        "claude-haiku-5-5"
    )

    # The SDK reads ANTHROPIC_API_KEY automatically.
    client = Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=256,
        system=(
            "You are an AI travel planning assistant. "
            "Use available transport search tools "
            "to investigate travel options. "
            "Do not invent prices or availability."
        ),
        tools=get_tool_definitions(),
        # Require a tool request for this specific lab.
        # Claude still decides WHICH available tool.
        #Configuration	Behavior
        #{"type": "any"}	At least one tool, possibly multiple
        #{"type": "any", "disable_parallel_tool_use": True}	Exactly one tool
        #{"type": "auto", "disable_parallel_tool_use": True}	Zero or one too
        
        #tool_choice={"type": "any"},

        # Force exactly one tool request in this API response.
        # Claude still decides whether to search trains or buses.
        tool_choice={
            "type": "any",
            "disable_parallel_tool_use": True
            },

        messages=[
            {
                "role": "user",
                "content": (
                    "Find transport from Toulouse to Paris "
                    "under 100 euros. Prefer trains. "
                    "Begin by searching for transport."
                )
            }
        ]
    )

    # stop_reason tells us why generation stopped.
    print("Stop reason:", response.stop_reason)

    # Responses contain structured content blocks.
    for block in response.content:
        if block.type == "tool_use":
            print("Selected tool:", block.name)
            print("Tool ID:", block.id)
            print("Arguments:", block.input)

    # Usage helps us monitor API consumption.
    print("Input tokens:", response.usage.input_tokens)
    print("Output tokens:", response.usage.output_tokens)


if __name__ == "__main__":
    main()
