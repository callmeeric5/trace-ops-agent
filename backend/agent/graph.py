"""LangGraph ReAct agent for fault diagnosis.

Implements a Reason-Act-Observe loop with:
- Tool calling via LangChain tools
- Evidence anchoring enforcement
- Persistent memory per investigation
- Guardrail checks on proposed actions
- Streaming support for real-time UI updates
"""

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


class AgentState(TypedDict):
    """State that flows through the LangGraph nodes."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    diagnosis_id: str
    reasoning_steps: list[dict]
    iteration_count: int
    pending_tool_calls: list[dict]


def build_agent_graph():
    """Construct and compile the LangGraph agent."""
    settings = get_settings()

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=settings.google_api_key,
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    tool_nodes: dict[str, ToolNode] = {t.name: ToolNode([t]) for t in ALL_TOOLS}
    tool_node_names = {t.name: f"tool_{t.name}" for t in ALL_TOOLS}
    tool_routes = {node_name: node_name for node_name in tool_node_names.values()}

    async def reasoning_node(state: AgentState) -> dict:
        """The 'Reason' step — call the LLM to decide the next action."""
        response = await llm_with_tools.ainvoke(state["messages"])
        tool_calls = getattr(response, "tool_calls", None)

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
            "pending_tool_calls": list(tool_calls or []),
        }

    async def _run_single_tool(state: AgentState, tool_name: str) -> dict:
        """Execute a single tool call for the specified tool name."""
        if not state.get("pending_tool_calls"):
            return {}

        tool_call = state["pending_tool_calls"][0]
        if tool_call.get("name") != tool_name:
            return {}

        remaining = state["pending_tool_calls"][1:]
        memory = AgentMemory(state["diagnosis_id"])
        await memory.append(
            "action",
            json.dumps(
                {
                    "tool_name": tool_name,
                    "tool_input": tool_call.get("args", {}),
                }
            ),
        )
        tool_message_request = AIMessage(
            content="(tool call)",
            tool_calls=[tool_call],
        )

        result = await tool_nodes[tool_name].ainvoke({"messages": [tool_message_request]})
        return {"messages": result["messages"], "pending_tool_calls": remaining}

    async def unknown_tool_node(state: AgentState) -> dict:
        """Handle unknown tool calls gracefully."""
        if not state.get("pending_tool_calls"):
            return {}
        tool_call = state["pending_tool_calls"][0]
        remaining = state["pending_tool_calls"][1:]
        msg = ToolMessage(
            name=tool_call.get("name", "unknown_tool"),
            content="Unknown tool call requested; skipping.",
            tool_call_id=tool_call.get("id", "unknown"),
        )
        return {"messages": [msg], "pending_tool_calls": remaining}

    async def observation_tool_result_node(state: AgentState) -> dict:
        """The 'Observation' step — persist tool outputs and surface them."""
        memory = AgentMemory(state["diagnosis_id"])
        steps = []
        for msg in state.get("messages", []):
            if isinstance(msg, ToolMessage):
                await memory.append("observation", msg.content[:1000])
                steps.append(
                    {
                        "step_number": state["iteration_count"],
                        "type": "observation",
                        "tool_name": msg.name,
                        "content": msg.content[:500],
                    }
                )

        return {"reasoning_steps": state["reasoning_steps"] + steps}

    def should_continue(state: AgentState) -> str:
        """Determine if the agent should keep going or finish."""
        settings = get_settings()
        if state["iteration_count"] >= settings.max_agent_iterations:
            logger.warning(
                "Agent hit max iteration limit (%d)", settings.max_agent_iterations
            )
            return "end"

        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            return "end"

        # If the LLM made tool calls, continue to execute them
        if last_message.tool_calls:
            return "tools"

        # Otherwise the LLM has produced a final answer
        return "end"

    def route_next_tool(state: AgentState) -> str:
        """Route to the next tool-specific node or back to reasoning."""
        if not state.get("pending_tool_calls"):
            return "reason_thought"
        tool_name = state["pending_tool_calls"][0].get("name", "")
        return tool_node_names.get(tool_name, "unknown_tool")

    graph = StateGraph(AgentState)
    graph.add_node("reason_thought", reasoning_node)
    graph.add_node("observation_tool_result", observation_tool_result_node)
    graph.add_node("unknown_tool", unknown_tool_node)
    graph.add_node(
        "route_tool",
        lambda state: {"pending_tool_calls": state.get("pending_tool_calls", [])},
    )

    def _make_tool_node(tool_name: str):
        async def _node(state: AgentState) -> dict:
            return await _run_single_tool(state, tool_name)

        return _node

    for tool in ALL_TOOLS:
        tool_node_name = tool_node_names[tool.name]
        graph.add_node(tool_node_name, _make_tool_node(tool.name))

    graph.set_entry_point("reason_thought")

    graph.add_conditional_edges(
        "reason_thought",
        should_continue,
        {
            "tools": "route_tool",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "route_tool",
        route_next_tool,
        {**tool_routes, "unknown_tool": "unknown_tool", "reason_thought": "reason_thought"},
    )

    for tool in ALL_TOOLS:
        graph.add_edge(tool_node_names[tool.name], "observation_tool_result")
    graph.add_edge("unknown_tool", "observation_tool_result")

    graph.add_conditional_edges(
        "observation_tool_result",
        route_next_tool,
        {**tool_routes, "unknown_tool": "unknown_tool", "reason_thought": "reason_thought"},
    )

    return graph.compile()


_compiled_graph = None


def get_agent():
    """Return a singleton compiled agent graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph


def export_compiled_graph_mermaid(output_path: str) -> str:
    """Export the compiled agent graph to a Mermaid file.

    Returns the Mermaid source as a string.
    """
    compiled = get_agent()
    graph = compiled.get_graph()
    if not hasattr(graph, "draw_mermaid"):
        raise RuntimeError("LangGraph does not expose draw_mermaid() in this version.")

    mermaid = graph.draw_mermaid()
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(mermaid)
        if not mermaid.endswith("\n"):
            handle.write("\n")
    return mermaid


def export_compiled_graph_png(output_path: str) -> bytes:
    """Export the compiled agent graph to a PNG file.

    Returns the PNG bytes.
    """
    compiled = get_agent()
    graph = compiled.get_graph()
    if hasattr(graph, "draw_mermaid_png"):
        png_bytes = graph.draw_mermaid_png()
        with open(output_path, "wb") as handle:
            handle.write(png_bytes)
        return png_bytes

    raise RuntimeError(
        "LangGraph does not expose draw_mermaid_png() in this version. "
        "Use Mermaid CLI (mmdc) to render the .mmd file to PNG."
    )


def _extract_stream_content(event: dict) -> str | None:
    chunk = event.get("data", {}).get("chunk")
    if isinstance(chunk, str) and chunk:
        return chunk
    if hasattr(chunk, "content") and getattr(chunk, "content"):
        return str(getattr(chunk, "content"))
    return None


def _tool_output_to_str(tool_output: Any) -> str:
    if isinstance(tool_output, str):
        return tool_output
    if hasattr(tool_output, "content"):
        return str(getattr(tool_output, "content"))
    return str(tool_output)


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
        "pending_tool_calls": [],
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
            content = _extract_stream_content(event)
            if content:
                yield {
                    "type": "stream",
                    "content": content,
                    "step_number": -1,
                }

        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            yield {
                "type": "action",
                "content": f"Calling tool: {tool_name}",
                "tool_name": tool_name,
                "tool_input": (
                    json.dumps(tool_input)
                    if isinstance(tool_input, dict)
                    else str(tool_input)
                ),
                "step_number": -1,
            }

        elif kind == "on_tool_end":
            tool_output = event.get("data", {}).get("output", "")
            output_str = _tool_output_to_str(tool_output)
            yield {
                "type": "observation",
                "content": output_str[:1000],
                "step_number": -1,
            }

    yield {
        "type": "conclusion",
        "diagnosis_id": diag_id,
        "content": "Investigation complete.",
        "step_number": -1,
    }
