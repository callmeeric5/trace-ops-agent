"use client";

import React from "react";
import { type ProposedAction } from "@/lib/api";
import { StatusBadge } from "./StatusBadge";

interface ActionsPanelProps {
  actions: ProposedAction[];
  onApprove: (actionId: string) => void;
  onReject: (actionId: string) => void;
}

export function ActionsPanel({ actions, onApprove, onReject }: ActionsPanelProps) {
  if (actions.length === 0) {
    return (
      <div className="text-center py-8 text-surface-500">
        <svg className="w-10 h-10 mx-auto mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
        </svg>
        <p className="text-sm">No pending actions</p>
        <p className="text-xs mt-1">Agent actions requiring approval will appear here</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {actions.map((action) => (
        <div key={action.action_id} className="glass-card p-4 animate-slide-up">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-mono ${
                action.action_type === "write"
                  ? "bg-red-500/15 text-red-400"
                  : "bg-emerald-500/15 text-emerald-400"
              }`}>
                {action.action_type.toUpperCase()}
              </span>
              <StatusBadge status={action.status} />
            </div>
            <span className={`text-xs ${
              action.risk_level === "high" || action.risk_level === "critical"
                ? "text-red-400"
                : action.risk_level === "medium"
                  ? "text-amber-400"
                  : "text-emerald-400"
            }`}>
              Risk: {action.risk_level}
            </span>
          </div>

          <p className="text-sm text-surface-200 mb-2">{action.description}</p>
          <code className="block text-xs bg-surface-900 text-surface-400 rounded p-2 font-mono mb-3">
            {action.command}
          </code>

          {action.status === "pending" && (
            <div className="flex gap-2">
              <button
                onClick={() => onApprove(action.action_id)}
                className="btn-success flex-1 justify-center text-xs"
              >
                ✓ Approve
              </button>
              <button
                onClick={() => onReject(action.action_id)}
                className="btn-danger flex-1 justify-center text-xs"
              >
                ✗ Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
