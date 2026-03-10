"""
Log Parser — handles both structured (JSON) and unstructured (stack traces) logs.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


# Common Python / Java stack trace pattern
_STACK_TRACE_RE = re.compile(
    r"(Traceback \(most recent call last\):.*?)(?=\n\S|\Z)",
    re.DOTALL,
)

_JAVA_EXCEPTION_RE = re.compile(
    r"((?:\w+\.)*\w+(?:Exception|Error):.*?)(?=\n\S|\Z)",
    re.DOTALL,
)


def parse_log_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise a raw log payload into a standard format.

    Accepts either:
    - Structured JSON with known fields (log_id, timestamp, service, level, message)
    - Raw text blobs / stack traces
    """
    # If it already has our standard fields, just fill in defaults
    if "log_id" in raw and "message" in raw:
        entry = {
            "log_id": raw["log_id"],
            "timestamp": raw.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "service": raw.get("service", "unknown"),
            "level": raw.get("level", "INFO").upper(),
            "message": raw["message"],
            "stack_trace": raw.get("stack_trace"),
            "extra": {},
        }
        # Collect everything else into extra
        known_keys = {"log_id", "timestamp", "service", "level", "message", "stack_trace", "extra"}
        for k, v in raw.items():
            if k not in known_keys:
                entry["extra"][k] = v
        # Merge any nested "extra" dict
        if isinstance(raw.get("extra"), dict):
            entry["extra"].update(raw["extra"])
        return entry

    # If it's a raw text blob, try to extract structure
    text = raw.get("raw", raw.get("text", json.dumps(raw)))
    entry = {
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": raw.get("service", "unknown"),
        "level": "ERROR",
        "message": "",
        "stack_trace": None,
        "extra": {},
    }

    # Try to extract stack traces
    st_match = _STACK_TRACE_RE.search(text)
    java_match = _JAVA_EXCEPTION_RE.search(text)

    if st_match:
        entry["stack_trace"] = st_match.group(1).strip()
        entry["message"] = text[: st_match.start()].strip() or "Stack trace detected"
    elif java_match:
        entry["stack_trace"] = java_match.group(1).strip()
        entry["message"] = text[: java_match.start()].strip() or "Java exception detected"
    else:
        entry["message"] = text[:500]

    return entry


def build_log_text(entry: dict[str, Any]) -> str:
    """
    Build a text representation of a log entry for embedding.
    Combines message + stack trace + extra fields.
    """
    parts = [
        f"[{entry.get('level', 'INFO')}] [{entry.get('service', 'unknown')}]",
        entry.get("message", ""),
    ]
    if entry.get("stack_trace"):
        parts.append(f"STACK TRACE: {entry['stack_trace']}")
    if entry.get("extra"):
        parts.append(f"CONTEXT: {json.dumps(entry['extra'])}")
    return " | ".join(parts)
