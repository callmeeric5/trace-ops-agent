"use client";

import React, { useState } from "react";

interface DiagnosisFormProps {
  onSubmit: (data: {
    alert_message: string;
    service_hint?: string;
    severity: string;
  }) => void;
  isLoading?: boolean;
}

export function DiagnosisForm({ onSubmit, isLoading }: DiagnosisFormProps) {
  const [alertMessage, setAlertMessage] = useState("");
  const [serviceHint, setServiceHint] = useState("");
  const [severity, setSeverity] = useState("high");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!alertMessage.trim()) return;
    onSubmit({
      alert_message: alertMessage,
      service_hint: serviceHint || undefined,
      severity,
    });
  };

  const presets = [
    { label: "Connection Pool Exhausted", message: "user-service is returning 503 errors — connection pool appears exhausted", service: "user-service" },
    { label: "Cache Penetration", message: "High latency on cache lookups. Cache miss rate > 80%. Possible cache penetration attack.", service: "cache-service" },
    { label: "Gateway Timeouts", message: "api-gateway returning 504 Gateway Timeout. Multiple downstream services unreachable.", service: "api-gateway" },
    { label: "Memory Leak", message: "api-gateway memory usage increasing steadily. Request history never cleared.", service: "api-gateway" },
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Preset Alerts */}
      <div>
        <label className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-2 block">
          Quick Presets
        </label>
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => {
                setAlertMessage(preset.message);
                setServiceHint(preset.service);
              }}
              className="text-xs px-3 py-1.5 rounded-lg bg-surface-800 border border-surface-700
                         hover:border-sentinel-500/50 hover:bg-surface-700 text-surface-300
                         transition-all duration-200"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      {/* Alert Message */}
      <div>
        <label htmlFor="alert-message" className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-1.5 block">
          Alert / Symptom Description
        </label>
        <textarea
          id="alert-message"
          value={alertMessage}
          onChange={(e) => setAlertMessage(e.target.value)}
          placeholder="Describe the production issue you're observing..."
          rows={3}
          className="input resize-none"
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Service Hint */}
        <div>
          <label htmlFor="service-hint" className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-1.5 block">
            Service (Optional)
          </label>
          <select
            id="service-hint"
            value={serviceHint}
            onChange={(e) => setServiceHint(e.target.value)}
            className="input"
          >
            <option value="">Auto-detect</option>
            <option value="api-gateway">api-gateway</option>
            <option value="user-service">user-service</option>
            <option value="cache-service">cache-service</option>
          </select>
        </div>

        {/* Severity */}
        <div>
          <label htmlFor="severity" className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-1.5 block">
            Severity
          </label>
          <select
            id="severity"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="input"
          >
            <option value="critical">🔴 Critical</option>
            <option value="high">🟠 High</option>
            <option value="medium">🟡 Medium</option>
            <option value="low">🟢 Low</option>
          </select>
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading || !alertMessage.trim()}
        className="btn-primary w-full justify-center disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Agent Investigating...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            Start Diagnosis
          </>
        )}
      </button>
    </form>
  );
}
