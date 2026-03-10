"""
LangGraph-based ReAct Agent for fault diagnosis.

Uses Gemini 2.5 as the LLM and implements the full ReAct loop:
  Thought → Action → Observation → (repeat) → Conclusion

Integrates:
  - Evidence anchoring (Killer Feature #1)
  - Noise reduction (Killer Feature #2)
  - Safety guardrails (Killer Feature #3)
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import google.generativeai as genai
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from app.config import settings
from app.agent.tools import TOOL_REGISTRY, TOOL_DESCRIPTIONS
from app.agent.prompts import build_system_prompt
from app.agent.memory import get_agent_memory
from app.api.sse import publish_event
from app.models.diagnosis import DiagnosisReport, DiagnosisStatus, ReasoningStep

logger = logging.getLogger("sentinel.agent.graph")

# ── Configure Gemini ──────────────────────────────────────────────────────────
genai.configure(api_key=settings.gemini_api_key)

MAX_STEPS = 10  # Safety limit to prevent infinite loops


# ── State Definition ──────────────────────────────────────────────────────────
class AgentState(TypedDict):
    diagnosis_id: str
    alert_message: str
    service_hint: Optional[str]
    messages: list[dict[str, str]]
    reasoning_trace: list[dict]
    evidence_log_ids: list[str]
    step_count: int
    status: str  # "reasoning", "acting", "concluded", "error"
    final_report: Optional[dict]


# ── Node Functions ────────────────────────────────────────────────────────────

async def reason_node(state: AgentState) -> AgentState:
    """
    REASON step: The agent analyzes the current state and decides what to do next.
    """
    diagnosis_id = state["diagnosis_id"]
    memory = get_agent_memory()

    # Build tool description string
    tool_desc = "\n".join(
        f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()
    )
    system_prompt = build_system_prompt(tool_desc)

    # Add investigation history summary
    inv_summary = memory.get_investigation_summary(diagnosis_id)

    # Build conversation for Gemini
    conversation = [{"role": "user", "parts": [system_prompt]}]
    for msg in state["messages"]:
        conversation.append({"role": msg["role"], "parts": [msg["content"]]})

    # Add current context
    context = (
        f"\nCurrent investigation: Step {state['step_count'] + 1}/{MAX_STEPS}\n"
        f"Investigation so far: {inv_summary}\n"
        f"Evidence collected: {len(state['evidence_log_ids'])} log entries\n\n"
        f"Based on the above, provide your next THOUGHT and decide on your next ACTION.\n"
        f"If you have enough evidence, state 'CONCLUSION:' followed by your diagnosis.\n\n"
        f"Format your response as:\n"
        f"THOUGHT: <your reasoning>\n"
        f"ACTION: <tool_name>\n"
        f"ACTION_INPUT: <json args>\n\n"
        f"OR if concluding:\n"
        f"THOUGHT: <your reasoning>\n"
        f"CONCLUSION: <your diagnosis>\n"
        f"ROOT_CAUSE: <root cause>\n"
        f"CONFIDENCE: <0.0-1.0>\n"
        f"EVIDENCE: <comma-separated log_ids>\n"
        f"ACTIONS: <recommended actions, one per line>"
    )
    conversation.append({"role": "user", "parts": [context]})

    try:
        model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")
        response = model.generate_content(
            [item for msg in conversation for item in msg["parts"]],
        )
        response_text = response.text.strip()
    except Exception as exc:
        logger.error(f"Gemini API error: {exc}")
        state["status"] = "error"
        state["messages"].append({
            "role": "model",
            "content": f"Error calling Gemini: {exc}",
        })
        return state

    # Parse the response
    state["messages"].append({"role": "model", "content": response_text})

    # Stream the thought to frontend
    await publish_event(diagnosis_id, "thought", {
        "step": state["step_count"] + 1,
        "content": response_text,
    })

    # Check if agent is concluding
    if "CONCLUSION:" in response_text:
        state["status"] = "concluded"
        # Parse conclusion
        report = _parse_conclusion(response_text, state)
        state["final_report"] = report
    else:
        state["status"] = "acting"
        # Parse action
        action_info = _parse_action(response_text)
        if action_info:
            state["messages"].append({
                "role": "user",
                "content": f"__PENDING_ACTION__:{json.dumps(action_info)}",
            })

    state["step_count"] += 1
    return state


async def act_node(state: AgentState) -> AgentState:
    """
    ACT step: Execute the tool chosen by the agent.
    """
    diagnosis_id = state["diagnosis_id"]
    memory = get_agent_memory()

    # Find the pending action
    pending = None
    for msg in reversed(state["messages"]):
        if msg["content"].startswith("__PENDING_ACTION__:"):
            pending = json.loads(msg["content"].replace("__PENDING_ACTION__:", ""))
            break

    if not pending:
        state["status"] = "reasoning"
        return state

    tool_name = pending.get("action", "")
    tool_input = pending.get("input", {})

    # Stream action to frontend
    await publish_event(diagnosis_id, "action", {
        "step": state["step_count"],
        "tool": tool_name,
        "input": tool_input,
    })

    # Execute tool
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if not tool_fn:
        observation = f"Unknown tool: {tool_name}. Available tools: {list(TOOL_REGISTRY.keys())}"
    else:
        try:
            result = tool_fn(**tool_input)
            observation = json.dumps(result, default=str)

            # Collect evidence log IDs
            evidence_ids = result.get("evidence_log_ids", [])
            state["evidence_log_ids"].extend(evidence_ids)

            # Record in memory
            memory.record_step(
                diagnosis_id=diagnosis_id,
                thought=f"Step {state['step_count']}",
                action=tool_name,
                action_input=tool_input,
                observation=observation[:500],
                evidence_log_ids=evidence_ids,
            )
        except Exception as exc:
            observation = f"Tool execution error: {exc}"

    # Stream observation to frontend
    await publish_event(diagnosis_id, "observation", {
        "step": state["step_count"],
        "tool": tool_name,
        "result_preview": observation[:500],
    })

    # Add reasoning step
    state["reasoning_trace"].append({
        "step_number": state["step_count"],
        "thought": pending.get("thought", ""),
        "action": tool_name,
        "action_input": tool_input,
        "observation": observation[:1000],
        "evidence_log_ids": state["evidence_log_ids"][-5:],
    })

    # Feed observation back
    state["messages"].append({
        "role": "user",
        "content": f"OBSERVATION from {tool_name}:\n{observation[:2000]}",
    })
    state["status"] = "reasoning"
    return state


def should_continue(state: AgentState) -> str:
    """Decide whether to continue the loop or end."""
    if state["status"] == "concluded":
        return "conclude"
    if state["status"] == "error":
        return "conclude"
    if state["step_count"] >= MAX_STEPS:
        return "conclude"
    if state["status"] == "acting":
        return "act"
    return "reason"


async def conclude_node(state: AgentState) -> AgentState:
    """Final node — publish the diagnosis report."""
    diagnosis_id = state["diagnosis_id"]

    if state.get("final_report"):
        await publish_event(diagnosis_id, "completed", state["final_report"])
    else:
        # Max steps reached or error
        await publish_event(diagnosis_id, "completed", {
            "diagnosis_id": diagnosis_id,
            "status": "completed",
            "summary": "Max investigation steps reached. See reasoning trace for partial findings.",
            "reasoning_trace": state["reasoning_trace"],
            "evidence_log_ids": state["evidence_log_ids"],
        })

    return state


# ── Graph Definition ──────────────────────────────────────────────────────────

def build_agent_graph() -> StateGraph:
    """Build the LangGraph state machine for the ReAct agent."""
    graph = StateGraph(AgentState)

    graph.add_node("reason", reason_node)
    graph.add_node("act", act_node)
    graph.add_node("conclude", conclude_node)

    graph.set_entry_point("reason")

    graph.add_conditional_edges(
        "reason",
        should_continue,
        {
            "act": "act",
            "reason": "reason",
            "conclude": "conclude",
        },
    )
    graph.add_conditional_edges(
        "act",
        should_continue,
        {
            "reason": "reason",
            "conclude": "conclude",
            "act": "act",
        },
    )
    graph.add_edge("conclude", END)

    return graph.compile()


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_diagnosis(
    diagnosis_id: str,
    alert_message: str,
    service_hint: Optional[str] = None,
) -> dict:
    """Run a full diagnosis session."""
    memory = get_agent_memory()
    memory.init_session(diagnosis_id)

    initial_state: AgentState = {
        "diagnosis_id": diagnosis_id,
        "alert_message": alert_message,
        "service_hint": service_hint,
        "messages": [
            {"role": "user", "content": f"ALERT: {alert_message}"},
        ],
        "reasoning_trace": [],
        "evidence_log_ids": [],
        "step_count": 0,
        "status": "reasoning",
        "final_report": None,
    }

    if service_hint:
        initial_state["messages"][0]["content"] += f"\nSuggested starting service: {service_hint}"

    # Check for similar past diagnoses
    past = memory.get_similar_past_diagnoses(alert_message)
    if past:
        initial_state["messages"].append({
            "role": "user",
            "content": f"HISTORICAL CONTEXT: Similar past diagnoses found:\n{json.dumps(past[:2], default=str)}",
        })

    graph = build_agent_graph()

    # Run the graph
    final_state = await graph.ainvoke(initial_state)

    return final_state.get("final_report", {
        "diagnosis_id": diagnosis_id,
        "status": "completed",
        "reasoning_trace": final_state.get("reasoning_trace", []),
        "evidence_log_ids": final_state.get("evidence_log_ids", []),
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_action(text: str) -> Optional[dict]:
    """Parse ACTION and ACTION_INPUT from agent response."""
    action = None
    action_input = {}
    thought = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("THOUGHT:"):
            thought = line.replace("THOUGHT:", "").strip()
        elif line.startswith("ACTION:"):
            action = line.replace("ACTION:", "").strip()
        elif line.startswith("ACTION_INPUT:"):
            try:
                action_input = json.loads(line.replace("ACTION_INPUT:", "").strip())
            except json.JSONDecodeError:
                action_input = {}

    if action:
        return {"action": action, "input": action_input, "thought": thought}
    return None


def _parse_conclusion(text: str, state: AgentState) -> dict:
    """Parse the conclusion from agent response."""
    conclusion = ""
    root_cause = ""
    confidence = 0.7
    recommended_actions = []

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("CONCLUSION:"):
            conclusion = line.replace("CONCLUSION:", "").strip()
        elif line.startswith("ROOT_CAUSE:"):
            root_cause = line.replace("ROOT_CAUSE:", "").strip()
        elif line.startswith("CONFIDENCE:"):
            try:
                confidence = float(line.replace("CONFIDENCE:", "").strip())
            except ValueError:
                pass
        elif line.startswith("ACTIONS:"):
            recommended_actions.append(line.replace("ACTIONS:", "").strip())
        elif line.startswith("- ") and recommended_actions:
            recommended_actions.append(line[2:].strip())

    return {
        "diagnosis_id": state["diagnosis_id"],
        "status": "completed",
        "summary": conclusion or "Diagnosis completed",
        "root_cause": root_cause,
        "confidence": confidence,
        "evidence_log_ids": state["evidence_log_ids"],
        "reasoning_trace": state["reasoning_trace"],
        "suggested_actions": recommended_actions,
    }
