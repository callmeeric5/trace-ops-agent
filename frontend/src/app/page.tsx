"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchLogs,
  fetchLogStats,
  fetchHealth,
  fetchDiagnoses,
  fetchDiagnosis,
  fetchPendingActions,
  createDiagnosis,
  approveAction,
  subscribeToDiagnosis,
  type LogEntry,
  type LogStats,
  type DiagnosisSession,
  type ReasoningStep,
  type ProposedAction,
  type SSEEvent,
} from "@/lib/api";
import { StatsCards } from "@/components/StatsCards";
import { DiagnosisForm } from "@/components/DiagnosisForm";
import { ReasoningTrace } from "@/components/ReasoningTrace";
import { LogViewer, LogDetailPanel } from "@/components/LogViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionsPanel } from "@/components/ActionsPanel";

type TabKey = "diagnose" | "logs" | "history";

export default function Dashboard() {
  // ── State ────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TabKey>("diagnose");
  const [isConnected, setIsConnected] = useState(false);
  const [stats, setStats] = useState<LogStats | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const [sessions, setSessions] = useState<DiagnosisSession[]>([]);
  const [activeDiagnosis, setActiveDiagnosis] = useState<DiagnosisSession | null>(null);
  const [liveSteps, setLiveSteps] = useState<ReasoningStep[]>([]);
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);
  const [pendingActions, setPendingActions] = useState<ProposedAction[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [logFilter, setLogFilter] = useState({ service: "", level: "", search: "" });
  const eventSourceRef = useRef<EventSource | null>(null);
  const traceEndRef = useRef<HTMLDivElement>(null);

  // ── Polling ──────────────────────────────────────────────────────────────
  const pollData = useCallback(async () => {
    try {
      const [healthRes, statsRes] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchLogStats().catch(() => null),
      ]);
      setIsConnected(!!healthRes);
      if (statsRes) setStats(statsRes);
    } catch {
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    pollData();
    const interval = setInterval(pollData, 5000);
    return () => clearInterval(interval);
  }, [pollData]);

  // Load logs when filter changes
  useEffect(() => {
    const loadLogs = async () => {
      try {
        const res = await fetchLogs({
          service: logFilter.service || undefined,
          level: logFilter.level || undefined,
          search: logFilter.search || undefined,
          limit: 200,
        });
        setLogs(res.logs);
      } catch {
        // ignore
      }
    };
    loadLogs();
    const interval = setInterval(loadLogs, 5000);
    return () => clearInterval(interval);
  }, [logFilter]);

  // Load sessions for history tab
  useEffect(() => {
    if (activeTab === "history") {
      fetchDiagnoses().then((res) => setSessions(res.sessions)).catch(() => {});
    }
  }, [activeTab]);

  // Auto-scroll reasoning trace
  useEffect(() => {
    traceEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveSteps]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleCreateDiagnosis = async (data: {
    alert_message: string;
    service_hint?: string;
    severity: string;
  }) => {
    setIsCreating(true);
    setLiveSteps([]);
    setActiveDiagnosis(null);

    try {
      const res = await createDiagnosis(data);
      const diagId = res.diagnosis_id;

      setActiveDiagnosis({
        diagnosis_id: diagId,
        status: "running",
        summary: `Investigating: ${data.alert_message}`,
        created_at: new Date().toISOString(),
      });
      setIsLiveStreaming(true);
      setActiveTab("diagnose");

      // Connect to SSE stream
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const source = subscribeToDiagnosis(
        diagId,
        (event: SSEEvent) => {
          switch (event.event) {
            case "thought":
              setLiveSteps((prev) => [
                ...prev,
                {
                  step_number: (event.data.step as number) || prev.length + 1,
                  thought: (event.data.content as string) || "",
                },
              ]);
              break;
            case "action":
              setLiveSteps((prev) => {
                const updated = [...prev];
                if (updated.length > 0) {
                  const last = updated[updated.length - 1];
                  updated[updated.length - 1] = {
                    ...last,
                    action: event.data.tool as string,
                    action_input: event.data.input as Record<string, unknown>,
                  };
                }
                return updated;
              });
              break;
            case "observation":
              setLiveSteps((prev) => {
                const updated = [...prev];
                if (updated.length > 0) {
                  const last = updated[updated.length - 1];
                  updated[updated.length - 1] = {
                    ...last,
                    observation: event.data.result_preview as string,
                  };
                }
                return updated;
              });
              break;
            case "completed":
            case "failed":
              setIsLiveStreaming(false);
              setIsCreating(false);
              // Refresh diagnosis report
              fetchDiagnosis(diagId)
                .then(setActiveDiagnosis)
                .catch(() => {});
              break;
            default:
              break;
          }
        },
        () => {
          setIsLiveStreaming(false);
          setIsCreating(false);
        }
      );
      eventSourceRef.current = source;
    } catch (err) {
      setIsCreating(false);
      console.error("Failed to create diagnosis:", err);
    }
  };

  const handleViewSession = async (id: string) => {
    try {
      const session = await fetchDiagnosis(id);
      setActiveDiagnosis(session);
      setLiveSteps(session.reasoning_trace || []);
      setActiveTab("diagnose");
    } catch {
      // ignore
    }
  };

  const handleApproveAction = async (actionId: string) => {
    try {
      await approveAction(actionId, true);
      const res = await fetchPendingActions();
      setPendingActions(res.actions);
    } catch {
      // ignore
    }
  };

  const handleRejectAction = async (actionId: string) => {
    try {
      await approveAction(actionId, false);
      const res = await fetchPendingActions();
      setPendingActions(res.actions);
    } catch {
      // ignore
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────
  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    {
      key: "diagnose",
      label: "Diagnose",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      ),
    },
    {
      key: "logs",
      label: "Logs",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
      ),
    },
    {
      key: "history",
      label: "History",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="min-h-screen">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-surface-800/50 bg-[var(--bg-primary)]/80 backdrop-blur-xl">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-sentinel-500 to-sentinel-700 flex items-center justify-center shadow-lg shadow-sentinel-500/25">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-surface-100 tracking-tight">
                Sentinel-Ops
                <span className="text-sentinel-400 ml-1.5">AI</span>
              </h1>
              <p className="text-[10px] text-surface-500 uppercase tracking-widest">
                Production Fault Diagnosis
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Connection Indicator */}
            <div className="flex items-center gap-2">
              <div className={`pulse-dot ${isConnected ? "bg-emerald-400" : "bg-red-400"}`} />
              <span className="text-xs text-surface-400">
                {isConnected ? "Connected" : "Disconnected"}
              </span>
            </div>
          </div>
        </div>

        {/* ── Tab Navigation ──────────────────────────────────────────────── */}
        <div className="max-w-[1600px] mx-auto px-6">
          <nav className="flex gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg
                  transition-all duration-200 border-b-2 -mb-px
                  ${activeTab === tab.key
                    ? "text-sentinel-400 border-sentinel-400 bg-sentinel-500/5"
                    : "text-surface-500 border-transparent hover:text-surface-300 hover:bg-surface-800/30"
                  }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* ── Main Content ───────────────────────────────────────────────────── */}
      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* Stats */}
        <StatsCards stats={stats} isConnected={isConnected} />

        {/* ── DIAGNOSE TAB ─────────────────────────────────────────────────── */}
        {activeTab === "diagnose" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left Column: Form + Reasoning Trace */}
            <div className="space-y-6">
              {/* New Diagnosis Form */}
              <div className="glass-card p-6">
                <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-sentinel-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
                  </svg>
                  New Investigation
                </h2>
                <DiagnosisForm onSubmit={handleCreateDiagnosis} isLoading={isCreating} />
              </div>

              {/* Reasoning Trace */}
              {(liveSteps.length > 0 || activeDiagnosis) && (
                <div className="glass-card p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider flex items-center gap-2">
                      <svg className="w-4 h-4 text-sentinel-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
                      </svg>
                      Reasoning Trace
                    </h2>
                    {activeDiagnosis && (
                      <StatusBadge status={activeDiagnosis.status} />
                    )}
                  </div>

                  <div className="max-h-[600px] overflow-y-auto pr-2">
                    <ReasoningTrace steps={liveSteps} isLive={isLiveStreaming} />
                    <div ref={traceEndRef} />
                  </div>

                  {/* Diagnosis Summary */}
                  {activeDiagnosis?.status === "completed" && activeDiagnosis.root_cause && (
                    <div className="mt-6 p-4 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                      <h3 className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-2">
                        🎯 Root Cause Identified
                      </h3>
                      <p className="text-sm text-surface-200 mb-3">{activeDiagnosis.root_cause}</p>
                      {activeDiagnosis.confidence !== undefined && (
                        <div className="flex items-center gap-2 mb-3">
                          <span className="text-xs text-surface-500">Confidence:</span>
                          <div className="flex-1 h-1.5 bg-surface-800 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-sentinel-500 to-emerald-400 rounded-full transition-all duration-1000"
                              style={{ width: `${(activeDiagnosis.confidence || 0) * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-sentinel-400 font-mono">
                            {Math.round((activeDiagnosis.confidence || 0) * 100)}%
                          </span>
                        </div>
                      )}
                      {activeDiagnosis.suggested_actions && activeDiagnosis.suggested_actions.length > 0 && (
                        <div>
                          <h4 className="text-xs text-surface-400 mb-1">Recommended Actions:</h4>
                          <ul className="space-y-1">
                            {activeDiagnosis.suggested_actions.map((action, i) => (
                              <li key={i} className="text-xs text-surface-300 flex items-start gap-2">
                                <span className="text-sentinel-400 mt-0.5">→</span>
                                {action}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right Column: Evidence / Logs + Actions */}
            <div className="space-y-6">
              {/* Evidence Logs */}
              <div className="glass-card p-6">
                <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-sentinel-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                  Evidence Fragments
                </h2>
                <div className="max-h-[500px] overflow-y-auto">
                  <LogViewer
                    logs={logs.slice(-50)}
                    highlightIds={activeDiagnosis?.evidence_log_ids || []}
                    onLogClick={setSelectedLog}
                  />
                </div>
              </div>

              {/* Selected Log Detail */}
              {selectedLog && (
                <LogDetailPanel log={selectedLog} onClose={() => setSelectedLog(null)} />
              )}

              {/* Pending Actions (Guardrails) */}
              <div className="glass-card p-6">
                <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                  </svg>
                  Safety Guardrails
                </h2>
                <ActionsPanel
                  actions={pendingActions}
                  onApprove={handleApproveAction}
                  onReject={handleRejectAction}
                />
              </div>
            </div>
          </div>
        )}

        {/* ── LOGS TAB ─────────────────────────────────────────────────────── */}
        {activeTab === "logs" && (
          <div className="glass-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider">
                Live Log Stream
              </h2>
              <span className="text-xs text-surface-500">{logs.length} entries</span>
            </div>

            {/* Filters */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <select
                value={logFilter.service}
                onChange={(e) => setLogFilter((f) => ({ ...f, service: e.target.value }))}
                className="input text-xs"
              >
                <option value="">All Services</option>
                <option value="api-gateway">api-gateway</option>
                <option value="user-service">user-service</option>
                <option value="cache-service">cache-service</option>
              </select>
              <select
                value={logFilter.level}
                onChange={(e) => setLogFilter((f) => ({ ...f, level: e.target.value }))}
                className="input text-xs"
              >
                <option value="">All Levels</option>
                <option value="CRITICAL">CRITICAL</option>
                <option value="ERROR">ERROR</option>
                <option value="WARN">WARN</option>
                <option value="INFO">INFO</option>
                <option value="DEBUG">DEBUG</option>
              </select>
              <input
                type="text"
                placeholder="Search logs..."
                value={logFilter.search}
                onChange={(e) => setLogFilter((f) => ({ ...f, search: e.target.value }))}
                className="input text-xs"
              />
            </div>

            <div className="max-h-[600px] overflow-y-auto">
              <LogViewer logs={logs} onLogClick={setSelectedLog} />
            </div>

            {selectedLog && (
              <div className="mt-4">
                <LogDetailPanel log={selectedLog} onClose={() => setSelectedLog(null)} />
              </div>
            )}
          </div>
        )}

        {/* ── HISTORY TAB ──────────────────────────────────────────────────── */}
        {activeTab === "history" && (
          <div className="glass-card p-6">
            <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider mb-4">
              Diagnosis History
            </h2>
            {sessions.length === 0 ? (
              <div className="text-center py-12 text-surface-500">
                <p className="text-sm">No diagnoses yet. Start your first investigation!</p>
              </div>
            ) : (
              <div className="space-y-3">
                {sessions.map((session) => (
                  <div
                    key={session.diagnosis_id}
                    onClick={() => handleViewSession(session.diagnosis_id)}
                    className="glass-card p-4 cursor-pointer hover:border-sentinel-500/40 transition-all duration-200"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <StatusBadge status={session.status} />
                      <span className="text-[10px] text-surface-500 font-mono">
                        {session.diagnosis_id.substring(0, 8)}
                      </span>
                    </div>
                    <p className="text-sm text-surface-200 mb-1">{session.summary}</p>
                    <div className="flex items-center gap-3 text-xs text-surface-500">
                      <span>{new Date(session.created_at).toLocaleString()}</span>
                      {session.severity && (
                        <span className={`${
                          session.severity === "critical" ? "text-red-400" :
                          session.severity === "high" ? "text-amber-400" :
                          "text-surface-400"
                        }`}>
                          ● {session.severity}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-surface-800/50 py-4 mt-12">
        <div className="max-w-[1600px] mx-auto px-6 flex items-center justify-between text-xs text-surface-600">
          <span>Sentinel-Ops AI v0.1.0</span>
          <span>Powered by Gemini 2.5 + LangGraph</span>
        </div>
      </footer>
    </div>
  );
}
