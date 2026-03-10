/**
 * API client utilities for the Sentinel-Ops backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

export interface LogEntry {
  log_id: string;
  timestamp: string;
  service: string;
  level: string;
  message: string;
  stack_trace?: string;
  extra?: Record<string, unknown>;
}

export interface LogStats {
  total_logs: number;
  by_service: Record<string, number>;
  by_level: Record<string, number>;
  latest_timestamp?: string;
}

export interface DiagnosisSession {
  diagnosis_id: string;
  status: string;
  summary: string;
  alert_message?: string;
  severity?: string;
  created_at: string;
  completed_at?: string;
  reasoning_trace?: ReasoningStep[];
  evidence_log_ids?: string[];
  suggested_actions?: string[];
  root_cause?: string;
  confidence?: number;
}

export interface ReasoningStep {
  step_number: number;
  thought: string;
  action?: string;
  action_input?: Record<string, unknown>;
  observation?: string;
  evidence_log_ids?: string[];
}

export interface ProposedAction {
  action_id: string;
  diagnosis_id: string;
  action_type: "read" | "write";
  description: string;
  command: string;
  risk_level: string;
  status: string;
  created_at: string;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

// ── API Calls ────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API error");
  }
  return res.json();
}

// ── Logs ─────────────────────────────────────────────────────────────────────

export async function fetchLogs(params?: {
  service?: string;
  level?: string;
  search?: string;
  limit?: number;
}): Promise<{ logs: LogEntry[]; count: number }> {
  const query = new URLSearchParams();
  if (params?.service) query.set("service", params.service);
  if (params?.level) query.set("level", params.level);
  if (params?.search) query.set("search", params.search);
  if (params?.limit) query.set("limit", String(params.limit));
  return apiFetch(`/api/v1/logs/?${query}`);
}

export async function fetchLogStats(): Promise<LogStats> {
  return apiFetch("/api/v1/logs/stats");
}

export async function fetchLogById(logId: string): Promise<LogEntry> {
  return apiFetch(`/api/v1/logs/${logId}`);
}

// ── Diagnosis ────────────────────────────────────────────────────────────────

export async function createDiagnosis(params: {
  alert_message: string;
  service_hint?: string;
  severity?: string;
}): Promise<{ diagnosis_id: string; status: string; stream_url: string }> {
  return apiFetch("/api/v1/diagnosis/", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function fetchDiagnoses(): Promise<{
  sessions: DiagnosisSession[];
  count: number;
}> {
  return apiFetch("/api/v1/diagnosis/");
}

export async function fetchDiagnosis(id: string): Promise<DiagnosisSession> {
  return apiFetch(`/api/v1/diagnosis/${id}`);
}

// ── Actions ──────────────────────────────────────────────────────────────────

export async function fetchPendingActions(): Promise<{
  actions: ProposedAction[];
  count: number;
}> {
  return apiFetch("/api/v1/actions/pending");
}

export async function approveAction(
  actionId: string,
  approved: boolean,
  approver: string = "admin"
): Promise<ProposedAction> {
  return apiFetch("/api/v1/actions/approve", {
    method: "POST",
    body: JSON.stringify({ action_id: actionId, approved, approver }),
  });
}

// ── SSE Streaming ────────────────────────────────────────────────────────────

export function subscribeToDiagnosis(
  diagnosisId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Event) => void
): EventSource {
  const source = new EventSource(
    `${API_BASE}/api/v1/stream/${diagnosisId}`
  );

  const eventTypes = [
    "connected",
    "thought",
    "action",
    "observation",
    "evidence",
    "approval_required",
    "completed",
    "failed",
    "keepalive",
  ];

  for (const type of eventTypes) {
    source.addEventListener(type, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ event: type, data });
      } catch {
        onEvent({ event: type, data: { raw: e.data } });
      }
    });
  }

  if (onError) {
    source.onerror = onError;
  }

  return source;
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<{
  status: string;
  log_count: number;
  gemini_configured: boolean;
}> {
  return apiFetch("/health");
}
