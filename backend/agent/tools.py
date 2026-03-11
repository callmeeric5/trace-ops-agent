"""Agent tools — callable functions the LangGraph agent can invoke."""

from typing import Optional
from langchain_core.tools import tool
from backend.db.database import async_session_factory
from backend.services.log_store import LogStore
from backend.services.noise_reducer import NoiseReducer
from backend.models.log_entry import LogLevel

MAX_TEXT_CHARS = 1000
STACK_TRACE_PREVIEW_CHARS = 300


def _truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _format_log_line(log, stack_trace_limit: int = STACK_TRACE_PREVIEW_CHARS) -> str:
    line = (
        f"[log_id={log.id}] {log.timestamp.isoformat()} "
        f"[{log.level}] {log.service}: {log.message}"
    )
    if log.stack_trace:
        line += f"\n  STACK_TRACE: {_truncate(log.stack_trace, stack_trace_limit)}"
    return line


def _format_log_id_list(log_ids: list[str], max_items: int = 5) -> str:
    if not log_ids:
        return ""
    preview = log_ids[:max_items]
    more = len(log_ids) - len(preview)
    suffix = f" ... (+{more} more)" if more > 0 else ""
    ids = ", ".join(preview)
    return f"[log_ids={ids}{suffix}]"


@tool
async def search_logs(
    service: Optional[str] = None,
    level: Optional[str] = None,
    keyword: Optional[str] = None,
    since_minutes: int = 60,
    limit: int = 100,
) -> str:
    """Search log entries with optional filters.

    Parameters
    ----------
    service : str, optional
        Filter by service name (e.g. 'order-service').
    level : str, optional
        Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    keyword : str, optional
        Full-text keyword search in the message body.
    since_minutes : int
        Look back this many minutes (default 60).
    limit : int
        Maximum number of results (default 100).
    """
    log_level = LogLevel(level) if level else None
    async with async_session_factory() as session:
        store = LogStore(session)
        logs = await store.query_logs(
            service=service,
            level=log_level,
            since_minutes=since_minutes,
            keyword=keyword,
            limit=limit,
        )
    if not logs:
        return "No log entries found matching the filters."

    lines = [_format_log_line(log) for log in logs]
    return "\n".join(lines)


@tool
async def get_log_by_id(log_id: str) -> str:
    """Fetch a single log entry by its ID.

    Parameters
    ----------
    log_id : str
        The unique identifier of the log entry.
    """
    async with async_session_factory() as session:
        store = LogStore(session)
        log = await store.get_by_id(log_id)
    if not log:
        return f"No log entry found with id={log_id}"
    parts = [
        f"id: {log.id}",
        f"timestamp: {log.timestamp.isoformat()}",
        f"service: {log.service}",
        f"level: {log.level}",
        f"message: {_truncate(log.message)}",
    ]
    if log.trace_id:
        parts.append(f"trace_id: {log.trace_id}")
    if log.stack_trace:
        parts.append(f"stack_trace: {_truncate(log.stack_trace)}")
    if log.metadata_json:
        parts.append(f"metadata: {_truncate(log.metadata_json)}")
    return "\n".join(parts)


@tool
async def get_error_summary(since_minutes: int = 60) -> str:
    """Get aggregate ERROR/CRITICAL counts grouped by service.

    Parameters
    ----------
    since_minutes : int
        Look back this many minutes (default 60).
    """
    async with async_session_factory() as session:
        store = LogStore(session)
        counts = await store.get_error_counts_by_service(since_minutes)
    if not counts:
        return "No errors or critical logs found in the given time window."
    lines = [f"{r['service']} [{r['level']}]: {r['count']} occurrences" for r in counts]
    return "\n".join(lines)


@tool
async def get_stack_traces(
    service: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Fetch the most recent stack traces, optionally filtered by service.

    Parameters
    ----------
    service : str, optional
        Filter by service name.
    limit : int
        Maximum number of stack traces (default 10).
    """
    async with async_session_factory() as session:
        store = LogStore(session)
        logs = await store.get_recent_stack_traces(service=service, limit=limit)
    if not logs:
        return "No stack traces found."
    lines: list[str] = []
    for log in logs:
        lines.append(
            f"[log_id={log.id}] {log.timestamp.isoformat()} "
            f"{log.service} [{log.level}]\n"
            f"  Message: {_truncate(log.message)}\n"
            f"  Stack Trace:\n{_truncate(log.stack_trace or '')}"
        )
    return "\n---\n".join(lines)


@tool
async def get_clustered_logs(
    service: Optional[str] = None,
    since_minutes: int = 60,
) -> str:
    """Fetch de-duplicated (clustered) log messages for a service.

    Similar log messages are grouped together. Each cluster shows the
    representative message and how many raw logs it represents.

    Parameters
    ----------
    service : str, optional
        Filter by service name.
    since_minutes : int
        Look back this many minutes (default 60).
    """
    async with async_session_factory() as session:
        store = LogStore(session)
        logs = await store.query_logs(
            service=service,
            since_minutes=since_minutes,
            limit=500,
        )
    if not logs:
        return "No log entries found."

    messages = [log.message for log in logs]
    ids = [log.id for log in logs]

    reducer = NoiseReducer()
    clusters = reducer.reduce(messages, ids)

    lines: list[str] = []
    for cluster in clusters:
        ids_preview = ", ".join(cluster.log_ids[:5])
        if len(cluster.log_ids) > 5:
            ids_preview += f" ... (+{len(cluster.log_ids) - 5} more)"
        first_log_id = cluster.log_ids[0] if cluster.log_ids else "unknown"
        lines.append(
            f"[cluster_size={cluster.cluster_size}] "
            f"{_truncate(cluster.representative_message)}\n"
            f"  [log_id={first_log_id}] {_format_log_id_list(cluster.log_ids)}\n"
            f"  log_ids: [{ids_preview}]"
        )
    return "\n".join(lines)


# Collect all tools for the agent graph
ALL_TOOLS = [
    search_logs,
    get_log_by_id,
    get_error_summary,
    get_stack_traces,
    get_clustered_logs,
]
