
"""
AI Travel Buddy - Claude Agent SDK Query Lab.

Objectives:
    CCDV-F: Understand query(), async messages and options.
    CCAR-F: Understand SDK-managed execution boundaries.

This is a text-only lab. No travel-search tools, file
operations or external browsing tools are enabled.

Run:
    uv run python -m app.agents.agent_sdk_query_lab
"""

import asyncio
import os

from dotenv import load_dotenv
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)


async def run_agent() -> None:
    """Execute one bounded, text-only Agent SDK query."""

    # Reuse the working authentication approach
    # from our earlier Messages API labs.
    load_dotenv(override=True)

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing from environment."
        )

    options = ClaudeAgentOptions(
        model="claude-haiku-5-5",
        system_prompt=(
            "You are an AI Travel Buddy learning assistant. "
            "Explain concepts precisely. Never invent actual "
            "transport prices or claim to have searched them."
        ),
        # Disable the base built-in tools for this lab.
        tools=[],
        # Do not auto-approve any additional tool operations.
        allowed_tools=[],
        permission_mode="dontAsk",
        # Isolate this lab from local Claude settings.
        setting_sources=[],
        max_turns=1,
        max_budget_usd=0.10,
    )

    prompt = (
        "Explain in two sentences why a travel-planning "
        "agent needs tools to compare train and bus prices."
    )

    # Unlike our handmade loop, the SDK manages the
    # underlying request and yields typed messages.
    async for message in query(
        prompt=prompt,
        options=options,
    ):
        print("SDK message type:", type(message).__name__)
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print("Claude:", block.text)

        elif isinstance(message, ResultMessage):
            print("Status:", message.subtype)
            print("Turns:", message.num_turns)

            if message.total_cost_usd is not None:
                print(
                    "Cost (USD):",
                    round(message.total_cost_usd, 4),
                )


if __name__ == "__main__":
    asyncio.run(run_agent())
