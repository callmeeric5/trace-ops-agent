"use client";

import React from "react";

interface StatusBadgeProps {
  status: string;
  pulse?: boolean;
}

export function StatusBadge({ status, pulse }: StatusBadgeProps) {
  const config: Record<string, { className: string; label: string }> = {
    running: { className: "badge-running", label: "Running" },
    starting: { className: "badge-running", label: "Starting" },
    completed: { className: "badge-completed", label: "Completed" },
    failed: { className: "badge-failed", label: "Failed" },
    pending: { className: "badge-pending", label: "Pending" },
    awaiting_approval: { className: "badge-pending", label: "Awaiting Approval" },
    healthy: { className: "badge-completed", label: "Healthy" },
    degraded: { className: "badge-pending", label: "Degraded" },
    critical: { className: "badge-failed", label: "Critical" },
  };

  const { className, label } = config[status] || {
    className: "badge bg-surface-700 text-surface-300 border border-surface-600",
    label: status,
  };

  return (
    <span className={className}>
      {(pulse || status === "running" || status === "starting") && (
        <span className="pulse-dot bg-current" />
      )}
      {label}
    </span>
  );
}

export function LogLevelBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    ERROR: "log-level-error",
    CRITICAL: "log-level-critical",
    WARN: "log-level-warn",
    WARNING: "log-level-warn",
    INFO: "log-level-info",
    DEBUG: "log-level-debug",
  };
  return <span className={map[level?.toUpperCase()] || "log-level"}>{level}</span>;
}
