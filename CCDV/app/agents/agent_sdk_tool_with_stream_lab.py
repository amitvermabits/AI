
"""
AI Travel Buddy - Lab 14: Agent SDK Custom Tool Execution with stream events

Messages API = You build the agent harness.

Agent SDK = Anthropic provides the agent harness; you configure and extend it.

Certification coverage:
    CCDV-F: Agent SDK, custom tools and execution loops.
    CCAR-F: Tool registration, permissions and orchestration.

Purpose:
    Register an existing Python function as an SDK tool.
    Observe Claude requesting the tool and the SDK executing it.

Important:
    Transport prices are MOCK data, not real-time fares.

Run:
    uv run python -m app.agents.agent_sdk_tool_lab
"""

import asyncio
import json
import os
from typing import Any
from claude_agent_sdk.types import StreamEvent

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)

from app.tools.transport import search_trains


# ----------------------------------------------------------
# STEP 1: Register our Python function as an SDK tool.
# ----------------------------------------------------------

@tool(
    "search_trains",
    "Search simulated train fares between two cities.",
    {
        "origin": str,
        "destination": str,
    },
)
async def search_trains_tool(
    args: dict[str, Any],
) -> dict[str, Any]:
    """
    Adapter between the Claude Agent SDK and our Python tool.

    Args:
        args: Validated tool arguments from the SDK.

    Returns:
        MCP-compatible content containing simulated train data.

    The Agent SDK invokes this function when Claude requests
    the registered search_trains tool.
    """

    origin = args["origin"]
    destination = args["destination"]

    print(
        f"\n[TOOL] Searching trains: "
        f"{origin} -> {destination}"
    )

    # Reuse the mock transport function from earlier labs.
    result = search_trains(origin, destination)

    print("[TOOL] Python function executed.")
    print("[TOOL] Result:", result)

    # SDK tools must return MCP-compatible content.
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result),
            }
        ]
    }


# ----------------------------------------------------------
# STEP 2: Configure and execute the agent.
# ----------------------------------------------------------

async def run_agent() -> None:
    """
    Run Claude with one explicitly permitted custom tool.

    Claude decides when to request the tool.
    The SDK handles dispatch and tool-result delivery.
    """

    load_dotenv(override=True)

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured."
        )

    # Register our Python tool through an in-process
    # MCP server. No separate MCP server process is needed.
    travel_server = create_sdk_mcp_server(
        name="travel",
        version="1.0.0",
        tools=[search_trains_tool],
    )

    options = ClaudeAgentOptions(
        model="claude-haiku-5-5",

        system_prompt=(
            "You are AI Travel Buddy. "
            "When asked for train fares, use search_trains. "
            "All tool results are simulated mock data. "
            "Never represent them as live or verified fares."
        ),

        # Disable built-in Claude Code tools.
        tools=[],

        # Register our custom tool server.
        mcp_servers={
            "travel": travel_server,
        },

        # Only this custom tool is automatically approved.
        allowed_tools=[
            "mcp__travel__search_trains",
        ],

        permission_mode="dontAsk",
        setting_sources=[],

        # Bound execution to avoid an uncontrolled loop.
        max_turns=3,
        max_budget_usd=0.10,
        #enables incremental output events.
        include_partial_messages=True,
    )

    # ClaudeSDKClient maintains the session and supports
    # in-process custom tool execution.
    async with ClaudeSDKClient(
        options=options
    ) as client:

        await client.query(
            "Use search_trains to find a train "
            "from Toulouse to Paris. "
            "Report the simulated fare."
        )

        # Process events emitted by the SDK.
        async for message in client.receive_response():

            print(
                "\nSDK Message:",
                type(message).__name__,
            )

            if isinstance(message, AssistantMessage):

                for block in message.content:

                    # Claude is requesting a tool.
                    if isinstance(block, ToolUseBlock):
                        print(
                            "[CLAUDE] Requested tool:",
                            block.name,
                        )
                        print(
                            "[CLAUDE] Arguments:",
                            block.input,
                        )

                    # Claude generated text.
                    elif isinstance(block, TextBlock):
                        print(
                            "[CLAUDE] Response:",
                            block.text,
                        )

            elif isinstance(message, ResultMessage):

                print("\n--- EXECUTION SUMMARY ---")
                print("Status:", message.subtype)
                print("Turns:", message.num_turns)

                if message.total_cost_usd is not None:
                    print(
                        "Cost (USD):",
                        round(message.total_cost_usd, 6),
                    )


        # --------------------------------------------------
        # LAB 13: Follow-up request in the SAME SDK session.
        # --------------------------------------------------

        print("\n--- SECOND REQUEST: SESSION MEMORY ---")

        # Submit another request using the same client.
        # The first request's context should be available.
        await client.query(
            "Without calling any tools, which two cities "
            "did I ask about in my previous request? "
            "Answer using only the two city names."
        )

        # Read the response for this second request.
        async for message in client.receive_response():

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(
                            "[SESSION MEMORY] Claude:",
                            block.text,
                        )
                    elif isinstance(block, ToolUseBlock):
                        print(
                            "[SESSION MEMORY] Unexpected tool:",
                            block.name,
                        )

            elif isinstance(message, ResultMessage):
                print(
                    "[SESSION MEMORY] Status:",
                    message.subtype,
                )
                print(
                    "[SESSION MEMORY] Turns:",
                    message.num_turns,
                )

        
        # --------------------------------------------------
        # LAB 14: Streaming output in the same client session.
        # --------------------------------------------------

        print("\n--- THIRD REQUEST: STREAMING OUTPUT ---")

        await client.query(
            "Without calling any tools, explain in four "
            "short sentences why simulated train fares "
            "must not be presented as live prices."
        )

        text_chunks: list[str] = []

        async for message in client.receive_response():

            # StreamEvent contains incremental API events.
            if isinstance(message, StreamEvent):
                event = message.event

                # Look specifically for a content update.
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})

                    # We want text, not partial tool JSON.
                    if delta.get("type") == "text_delta":
                        chunk = delta.get("text", "")

                        if chunk:
                            text_chunks.append(chunk)

                            # Print without waiting for
                            # the entire AssistantMessage.
                            print(
                                chunk,
                                end="",
                                flush=True,
                            )

            # AssistantMessage objects may also arrive,
            # but we avoid printing their text again.

            elif isinstance(message, ResultMessage):
                print("\n\n--- STREAMING SUMMARY ---")
                print("Status:", message.subtype)
                print("Turns:", message.num_turns)
                print("Text chunks:", len(text_chunks))
                print(
                    "Characters received:",
                    len("".join(text_chunks)),
                )

# ----------------------------------------------------------
# STEP 3: Python entry point.
# ----------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(run_agent())
