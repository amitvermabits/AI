
"""
AI Travel Buddy - Bounded Agent Loop.

Certification:
    CCDV-F | Domain 1 | Skill 1.1 - Agent Architecture

Learning objectives:
    1. Implement an iterative Claude tool-use loop.
    2. Preserve conversation history across API calls.
    3. Execute tools and return structured observations.
    4. Detect completion using stop_reason.
    5. Enforce a maximum number of tool executions.

Architecture:
    User -> Claude -> Tool -> Observation -> Claude
                         ^                   |
                         |___________________|

Safety:
    - Only registered Python tools can execute.
    - Maximum of 3 tool executions per request.
    - A final response is requested without further tools
      once the execution limit is reached.
    - All transport prices are simulated.

Run from the project root:
    uv run python -m app.agents.agent_loop_lab
"""

import json
import os
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

from app.agents.tool_selection_lab import get_tool_definitions
from app.agents.tool_execution_lab import execute_tool


# Maximum number of Python tools the agent may execute.
# This is different from max_tokens, which limits
# the length of each Claude response.
MAX_TOOL_CALLS = 3


def run_agent(user_request: str) -> None:
    """
    Execute a bounded Claude agent loop.

    Args:
        user_request:
            The user's transport planning request.

    Returns:
        None. Prints tool decisions and the final response.

    Algorithm:
        1. Ask Claude what action to take.
        2. If Claude requests a tool, execute it.
        3. Append the observation to conversation history.
        4. Repeat until Claude finishes.
        5. Stop further tool calls at the execution limit.

    Note:
        An end_turn response indicates that Claude
        finished its turn, not necessarily that a
        suitable transport option was found.
    """

    load_dotenv(override=True)

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is missing")

    client = Anthropic()

    model = os.getenv(
        "CLAUDE_MODEL",
        "claude-haiku-5-5",
    )

    # Preserve the full conversation across iterations.
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": user_request,
        }
    ]

    system_prompt = (
        "You are AI Travel Buddy, a travel assistant. "
        "Prefer trains when affordable. "
        "If a train is above the user's budget, "
        "consider searching buses. "
        "Treat all tool prices as simulated data, "
        "not live fares. "
        "Never invent fares, availability or searches. "
        "If search opportunities are exhausted, "
        "explain any remaining uncertainty."
    )

    total_input_tokens = 0
    total_output_tokens = 0

    # There can be at most 3 tool rounds, followed
    # by one final response without tool access.
    for round_index in range(MAX_TOOL_CALLS + 1):

        if round_index == MAX_TOOL_CALLS:
            # Safety limit reached: no more tools.
            tool_choice = {"type": "none"}

            print(
                "\nTool limit reached. "
                "Requesting a final response."
            )

        elif round_index == 0:
            # For this lab, require one initial tool.
            tool_choice = {
                "type": "any",
                "disable_parallel_tool_use": True,
            }

        else:
            # On later rounds, Claude may either
            # request one tool or finish answering.
            tool_choice = {
                "type": "auto",
                "disable_parallel_tool_use": True,
            }

        # Ask Claude to decide its next action.
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=system_prompt,
            tools=get_tool_definitions(),
            tool_choice=tool_choice,
            messages=messages,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        print("\nStop reason:", response.stop_reason)

        # CASE 1: Claude has finished its response.
        if response.stop_reason == "end_turn":

            print("\n--- CLAUDE'S FINAL RESPONSE ---")

            for block in response.content:
                if block.type == "text":
                    print(block.text)

            break

        # CASE 2: Claude requested a Python tool.
        elif response.stop_reason == "tool_use":

            tool_blocks = [
                block
                for block in response.content
                if block.type == "tool_use"
            ]

            if len(tool_blocks) != 1:
                raise RuntimeError(
                    "Expected exactly one tool request."
                )

            tool_request = tool_blocks[0]

            print("Tool:", tool_request.name)
            print("Arguments:", tool_request.input)

            # Execute the approved Python tool.
            result = execute_tool(
                tool_request.name,
                tool_request.input,
            )

            print("Observation:", result)

            # First preserve Claude's tool request.
            messages.append({
                "role": "assistant",
                "content": response.content,
            })

            # Then send the matching tool result.
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_request.id,
                        "content": json.dumps(result),
                        "is_error": "error" in result,
                    }
                ],
            })

            # The next iteration sends the updated
            # conversation back to Claude.

        # CASE 3: Unexpected or incomplete response.
        else:
            print(
                "Agent stopped without a final answer.",
                "Reason:",
                response.stop_reason,
            )
            break

    print("\n--- TOKEN USAGE ---")
    print("Total input tokens:", total_input_tokens)
    print("Total output tokens:", total_output_tokens)


def main() -> None:
    """
    Start the lab with our simulated travel scenario.
    """

    run_agent(
        "Find transport from Toulouse to Paris "
        "for less than 100 EUR. Prefer trains. "
        "Search before recommending an option."
    )


if __name__ == "__main__":
    main()
