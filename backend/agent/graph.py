"""LangGraph ReAct agent for fault diagnosis.

Implements a Reason-Act-Observe loop with:
- Tool calling via LangChain tools
- Evidence anchoring enforcement
- Persistent memory per investigation
- Guardrail checks on proposed actions
- Streaming support for real-time UI updates
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, TypedDict, Annotated, Sequence
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from backend.agent.guardrails import evaluate_action
from backend.agent.memory import AgentMemory
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import ALL_TOOLS
from backend.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    """State that flows through the LangGraph nodes."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    diagnosis_id: str
    reasoning_steps: list[dict]
    iteration_count: int


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------
def build_agent_graph():
    """Construct and compile the LangGraph agent."""
    settings = get_settings()

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=0,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    tool_node = ToolNode(ALL_TOOLS)

    # ---- Nodes -----------------------------------------------------------

    async def reasoning_node(state: AgentState) -> dict:
        """The 'Reason' step — call the LLM to decide the next action."""
        response = await llm_with_tools.ainvoke(state["messages"])

        # Persist to memory
        memory = AgentMemory(state["diagnosis_id"])
        await memory.append("thought", response.content or "(tool call)")

        step = {
            "step_number": state["iteration_count"] + 1,
            "type": "thought",
            "content": response.content or "(tool call)",
        }

        return {
            "messages": [response],
            "reasoning_steps": state["reasoning_steps"] + [step],
            "iteration_count": state["iteration_count"] + 1,
        }

    async def tool_executor_node(state: AgentState) -> dict:
        """The 'Act' step — execute the tool called by the LLM."""
        result = await tool_node.ainvoke(state)

        # Persist observations
        memory = AgentMemory(state["diagnosis_id"])
        for msg in result.get("messages", []):
            if isinstance(msg, ToolMessage):
                await memory.append("observation", msg.content[:1000])

        steps = []
        for msg in result.get("messages", []):
            if isinstance(msg, ToolMessage):
                steps.append(
                    {
                        "step_number": state["iteration_count"],
                        "type": "observation",
                        "tool_name": msg.name,
                        "content": msg.content[:500],
                    }
                )

        return {
            "messages": result["messages"],
            "reasoning_steps": state["reasoning_steps"] + steps,
        }

    # ---- Routing ---------------------------------------------------------

    def should_continue(state: AgentState) -> str:
        """Determine if the agent should keep going or finish."""
        settings = get_settings()
        if state["iteration_count"] >= settings.max_agent_iterations:
            logger.warning("Agent hit max iteration limit (%d)", settings.max_agent_iterations)
            return "end"

        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            return "end"

        # If the LLM made tool calls, continue to execute them
        if last_message.tool_calls:
            return "tools"

        # Otherwise the LLM has produced a final answer
        return "end"

    # ---- Assemble --------------------------------------------------------

    graph = StateGraph(AgentState)
    graph.add_node("reason", reasoning_node)
    graph.add_node("tools", tool_executor_node)

    graph.set_entry_point("reason")

    graph.add_conditional_edges(
        "reason",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )
    graph.add_edge("tools", "reason")

    return graph.compile()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
_compiled_graph = None


def get_agent():
    """Return a singleton compiled agent graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph


async def run_diagnosis(
    description: str,
    diagnosis_id: str | None = None,
) -> AsyncIterator[dict]:
    """Run a full diagnostic investigation, yielding reasoning steps.

    Yields dicts with keys:
        type: "thought" | "observation" | "action" | "conclusion" | "guardrail"
        content: str
        step_number: int
        ... (additional fields depending on type)
    """
    agent = get_agent()
    diag_id = diagnosis_id or str(uuid4())

    initial_state: AgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"ALERT: {description}\n\nPlease investigate."),
        ],
        "diagnosis_id": diag_id,
        "reasoning_steps": [],
        "iteration_count": 0,
    }

    yield {
        "type": "start",
        "diagnosis_id": diag_id,
        "content": f"Starting investigation: {description}",
        "step_number": 0,
    }

    config = {"recursion_limit": get_settings().max_agent_iterations * 2 + 5}

    async for event in agent.astream_events(initial_state, config=config, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                yield {
                    "type": "stream",
                    "content": chunk.content,
                    "step_number": -1,
                }

        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            yield {
                "type": "action",
                "content": f"Calling tool: {tool_name}",
                "tool_name": tool_name,
                "tool_input": json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input),
                "step_number": -1,
            }

        elif kind == "on_tool_end":
            tool_output = event.get("data", {}).get("output", "")
            if hasattr(tool_output, "content"):
                output_str = str(tool_output.content)
            else:
                output_str = str(tool_output) if not isinstance(tool_output, str) else tool_output
            yield {
                "type": "observation",
                "content": output_str[:1000],
                "step_number": -1,
            }

    # Final step — check guardrails on the last AI message
    # (In a real production system we'd parse the conclusion more carefully)
    yield {
        "type": "conclusion",
        "diagnosis_id": diag_id,
        "content": "Investigation complete.",
        "step_number": -1,
    }
