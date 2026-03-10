"use client";

import React from "react";
import { type ReasoningStep } from "@/lib/api";

interface ReasoningTraceProps {
  steps: ReasoningStep[];
  isLive?: boolean;
}

export function ReasoningTrace({ steps, isLive }: ReasoningTraceProps) {
  if (steps.length === 0 && !isLive) {
    return (
      <div className="text-center py-12 text-surface-500">
        <svg className="w-12 h-12 mx-auto mb-4 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
        </svg>
        <p className="text-sm">No reasoning steps yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {steps.map((step, idx) => (
        <div key={idx} className="animate-slide-up" style={{ animationDelay: `${idx * 0.1}s` }}>
          {/* THOUGHT */}
          {step.thought && (
            <div className="reasoning-step step-thought">
              <div className="mb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-sentinel-400">
                  💭 Thought — Step {step.step_number}
                </span>
              </div>
              <p className="text-sm text-surface-200 leading-relaxed">{step.thought}</p>
            </div>
          )}

          {/* ACTION */}
          {step.action && (
            <div className="reasoning-step step-action">
              <div className="mb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                  ⚡ Action
                </span>
              </div>
              <div className="flex items-center gap-2 mb-1">
                <code className="text-xs bg-amber-500/10 text-amber-300 px-2 py-0.5 rounded font-mono">
                  {step.action}
                </code>
              </div>
              {step.action_input && (
                <pre className="text-xs text-surface-400 bg-surface-900/50 rounded p-2 overflow-x-auto font-mono">
                  {JSON.stringify(step.action_input, null, 2)}
                </pre>
              )}
            </div>
          )}

          {/* OBSERVATION */}
          {step.observation && (
            <div className="reasoning-step step-observation">
              <div className="mb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
                  👁 Observation
                </span>
              </div>
              <div className="text-xs text-surface-300 bg-surface-900/50 rounded p-3 max-h-40 overflow-y-auto font-mono leading-relaxed">
                {step.observation.length > 500
                  ? step.observation.substring(0, 500) + "..."
                  : step.observation}
              </div>
              {step.evidence_log_ids && step.evidence_log_ids.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {step.evidence_log_ids.slice(0, 5).map((id) => (
                    <span key={id} className="text-[10px] bg-sentinel-500/15 text-sentinel-300 px-1.5 py-0.5 rounded font-mono">
                      📎 {id.substring(0, 8)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* Live typing indicator */}
      {isLive && (
        <div className="reasoning-step step-thought">
          <div className="typing-indicator flex gap-1 py-2">
            <span className="w-1.5 h-1.5 rounded-full bg-sentinel-400" />
            <span className="w-1.5 h-1.5 rounded-full bg-sentinel-400" />
            <span className="w-1.5 h-1.5 rounded-full bg-sentinel-400" />
          </div>
        </div>
      )}
    </div>
  );
}
