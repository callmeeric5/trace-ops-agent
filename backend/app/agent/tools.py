"""
Agent Tools — Functions the ReAct agent can invoke.

Each tool returns evidence-anchored results (with log_ids).
"""

import logging
from typing import Any, Optional

from app.storage.database import get_log_database
from app.storage.chroma_store import get_chroma_store
from app.ingestion.noise_filter import NoiseFilter

logger = logging.getLogger("sentinel.agent.tools")


def get_pod_logs(
    service: str,
    level: Optional[str] = None,
    limit: int = 50,
    search: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve logs for a specific service/pod.
    Returns log entries with their log_ids for evidence anchoring.
    """
    db = get_log_database()
    logs = db.query(service=service, level=level, limit=limit, search=search)
    return {
        "tool": "get_pod_logs",
        "service": service,
        "count": len(logs),
        "logs": logs,
        "evidence_log_ids": [l["log_id"] for l in logs],
    }


def search_similar_errors(query: str, n_results: int = 10, service: Optional[str] = None) -> dict[str, Any]:
    """
    Semantic search for errors similar to the query.
    Uses ChromaDB vector similarity.
    """
    store = get_chroma_store()
    where = {"service": service} if service else None
    results = store.search_similar(query, n_results=n_results, where=where)
    return {
        "tool": "search_similar_errors",
        "query": query,
        "count": len(results),
        "results": results,
        "evidence_log_ids": [r["log_id"] for r in results],
    }


def check_service_health(service: str) -> dict[str, Any]:
    """
    Check the health status and recent error rate of a service.
    """
    db = get_log_database()
    all_logs = db.query(service=service, limit=200)
    errors = [l for l in all_logs if l.get("level") in ("ERROR", "CRITICAL")]
    warnings = [l for l in all_logs if l.get("level") == "WARN"]

    total = len(all_logs)
    error_rate = len(errors) / total if total > 0 else 0

    # Determine health status
    if error_rate > 0.3:
        status = "critical"
    elif error_rate > 0.1:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "tool": "check_service_health",
        "service": service,
        "status": status,
        "total_logs": total,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "error_rate": round(error_rate, 4),
        "recent_errors": errors[:5],
        "evidence_log_ids": [e["log_id"] for e in errors[:5]],
    }


def get_recent_changes() -> dict[str, Any]:
    """
    Simulate checking git history / recent deployments.
    Returns mock change history for investigation.
    """
    # Simulated git log
    changes = [
        {
            "commit": "a1b2c3d",
            "author": "dev@example.com",
            "date": "2026-03-10T10:30:00Z",
            "message": "feat: update connection pool settings",
            "files_changed": ["services/user-service/main.py", "docker-compose.yml"],
        },
        {
            "commit": "e4f5g6h",
            "author": "ops@example.com",
            "date": "2026-03-10T09:15:00Z",
            "message": "fix: increase Redis timeout to 5s",
            "files_changed": ["services/cache-service/main.py"],
        },
        {
            "commit": "i7j8k9l",
            "author": "dev@example.com",
            "date": "2026-03-09T16:45:00Z",
            "message": "refactor: remove connection release in error path",
            "files_changed": ["services/user-service/main.py"],
        },
    ]
    return {
        "tool": "get_recent_changes",
        "count": len(changes),
        "changes": changes,
    }


def get_noise_reduced_errors(service: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    """
    Get deduplicated, representative error samples.
    Killer Feature #2: Noise Reduction
    """
    noise_filter = NoiseFilter()
    representative = noise_filter.get_representative_errors(service=service, limit=limit)
    return {
        "tool": "get_noise_reduced_errors",
        "service": service,
        "original_count": "unknown (pre-filtered)",
        "representative_count": len(representative),
        "logs": representative,
        "evidence_log_ids": [r.get("log_id", "") for r in representative],
    }


# Tool registry for the agent
TOOL_REGISTRY = {
    "get_pod_logs": get_pod_logs,
    "search_similar_errors": search_similar_errors,
    "check_service_health": check_service_health,
    "get_recent_changes": get_recent_changes,
    "get_noise_reduced_errors": get_noise_reduced_errors,
}

TOOL_DESCRIPTIONS = {
    "get_pod_logs": "Retrieve logs for a specific service. Args: service (str), level (optional str), limit (optional int), search (optional str)",
    "search_similar_errors": "Semantic search for errors similar to a query. Args: query (str), n_results (optional int), service (optional str)",
    "check_service_health": "Check health status and error rate of a service. Args: service (str)",
    "get_recent_changes": "Check recent git commits / deployments. No args required.",
    "get_noise_reduced_errors": "Get deduplicated representative error samples. Args: service (optional str), limit (optional int)",
}
