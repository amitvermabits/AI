
"""
AI Travel Buddy - Lab 15: Agent SDK Streaming Input.

Certification objectives:
    CCDV-F: Async generators and Agent SDK input modes.
    CCAR-F: Understand asynchronous input handling.

Purpose:
    Demonstrate how a Python async generator supplies
    structured user input to ClaudeSDKClient.

No tools or real travel searches are enabled.

Run:
    uv run python -m app.agents.agent_sdk_streaming_input_lab
"""

import asyncio
import os
from typing import Any, AsyncIterator

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)


async def travel_input_stream() -> AsyncIterator[dict[str, Any]]:
    """
    Yield one structured travel request asynchronously.

    In a future implementation, the values can come
    from the application's validated input layer.
    """

    trip = {
        "origin": "Toulouse",
        "destination": "Paris",
        "travelers": 4,
        "budget_eur": 300,
    }

    prompt = (
        "Summarize this trip request using only the "
        "provided information. Do not use tools or "
        "invent transport prices.\n"
        f"Origin: {trip['origin']}\n"
        f"Destination: {trip['destination']}\n"
        f"Travelers: {trip['travelers']}\n"
        f"Budget: EUR {trip['budget_eur']}"
    )

    print("[INPUT] Preparing travel request")

    # Yield a structured SDK user message.
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": prompt,
        },
    }


async def run_agent() -> None:
    """Send asynchronous input and inspect SDK output."""

    load_dotenv(override=True)

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is missing.")

    options = ClaudeAgentOptions(
        model="claude-haiku-5-5",
        system_prompt=(
            "You are AI Travel Buddy. "
            "Summarize travel requests accurately."
        ),
        tools=[],
        allowed_tools=[],
        permission_mode="dontAsk",
        setting_sources=[],
        max_turns=1,
        max_budget_usd=0.10,
    )

    async with ClaudeSDKClient(options=options) as client:

        # Pass the async generator, not a string.
        await client.query(travel_input_stream())

        async for message in client.receive_response():

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print("[CLAUDE]", block.text)

            elif isinstance(message, ResultMessage):
                print("[RESULT] Status:", message.subtype)
                print("[RESULT] Turns:", message.num_turns)
                print("[RESULT] Cost:", message.total_cost_usd)


if __name__ == "__main__":
    asyncio.run(run_agent())
