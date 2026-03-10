"use client";

import React from "react";
import { LogLevelBadge } from "./StatusBadge";
import { type LogEntry } from "@/lib/api";

interface LogViewerProps {
  logs: LogEntry[];
  highlightIds?: string[];
  onLogClick?: (log: LogEntry) => void;
}

export function LogViewer({ logs, highlightIds = [], onLogClick }: LogViewerProps) {
  if (logs.length === 0) {
    return (
      <div className="text-center py-12 text-surface-500">
        <svg className="w-12 h-12 mx-auto mb-4 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
        <p className="text-sm">No logs to display</p>
      </div>
    );
  }

  return (
    <div className="space-y-1 font-mono text-xs">
      {logs.map((log, idx) => {
        const isHighlighted = highlightIds.includes(log.log_id);

        return (
          <div
            key={log.log_id || idx}
            onClick={() => onLogClick?.(log)}
            className={`
              flex items-start gap-3 px-3 py-2 rounded-lg cursor-pointer
              transition-all duration-200 group
              ${isHighlighted
                ? "bg-sentinel-500/15 border border-sentinel-500/30 animate-glow"
                : "hover:bg-surface-800/50 border border-transparent"
              }
            `}
          >
            {/* Timestamp */}
            <span className="text-surface-500 whitespace-nowrap shrink-0 text-[11px]">
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>

            {/* Level */}
            <span className="shrink-0">
              <LogLevelBadge level={log.level} />
            </span>

            {/* Service */}
            <span className="text-accent-cyan shrink-0 text-[11px]">
              [{log.service}]
            </span>

            {/* Message */}
            <span className={`flex-1 break-all ${isHighlighted ? "text-surface-100" : "text-surface-300"}`}>
              {log.message}
            </span>

            {/* Log ID chip */}
            {isHighlighted && (
              <span className="text-[9px] bg-sentinel-500/20 text-sentinel-300 px-1.5 py-0.5 rounded shrink-0">
                📎 Evidence
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface LogDetailPanelProps {
  log: LogEntry;
  onClose: () => void;
}

export function LogDetailPanel({ log, onClose }: LogDetailPanelProps) {
  return (
    <div className="glass-card p-4 animate-slide-up">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-surface-100">Log Detail</h3>
        <button onClick={onClose} className="text-surface-500 hover:text-surface-300 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="space-y-3 text-xs">
        <div className="flex gap-2">
          <span className="text-surface-500 w-20">Log ID</span>
          <code className="text-sentinel-300 font-mono">{log.log_id}</code>
        </div>
        <div className="flex gap-2">
          <span className="text-surface-500 w-20">Timestamp</span>
          <span className="text-surface-200">{log.timestamp}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-surface-500 w-20">Service</span>
          <span className="text-accent-cyan">{log.service}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-surface-500 w-20">Level</span>
          <LogLevelBadge level={log.level} />
        </div>
        <div>
          <span className="text-surface-500 block mb-1">Message</span>
          <p className="text-surface-200 bg-surface-900 rounded p-2 font-mono">{log.message}</p>
        </div>
        {log.stack_trace && (
          <div>
            <span className="text-surface-500 block mb-1">Stack Trace</span>
            <pre className="text-red-300 bg-red-500/5 border border-red-500/10 rounded p-2 font-mono overflow-x-auto whitespace-pre-wrap">
              {log.stack_trace}
            </pre>
          </div>
        )}
        {log.extra && Object.keys(log.extra).length > 0 && (
          <div>
            <span className="text-surface-500 block mb-1">Extra Context</span>
            <pre className="text-surface-300 bg-surface-900 rounded p-2 font-mono overflow-x-auto">
              {JSON.stringify(log.extra, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
