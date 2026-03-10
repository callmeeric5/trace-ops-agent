"use client";

import React from "react";
import { type LogStats } from "@/lib/api";

interface StatsCardsProps {
  stats: LogStats | null;
  isConnected: boolean;
}

export function StatsCards({ stats, isConnected }: StatsCardsProps) {
  const cards = [
    {
      label: "Total Logs",
      value: stats?.total_logs?.toLocaleString() ?? "—",
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
      ),
      color: "text-sentinel-400",
      bgColor: "bg-sentinel-500/10",
    },
    {
      label: "Errors",
      value: ((stats?.by_level?.["ERROR"] ?? 0) + (stats?.by_level?.["CRITICAL"] ?? 0)).toLocaleString(),
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
        </svg>
      ),
      color: "text-red-400",
      bgColor: "bg-red-500/10",
    },
    {
      label: "Warnings",
      value: (stats?.by_level?.["WARN"] ?? 0).toLocaleString(),
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
      ),
      color: "text-amber-400",
      bgColor: "bg-amber-500/10",
    },
    {
      label: "Backend",
      value: isConnected ? "Online" : "Offline",
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.808-3.808-9.98 0-13.788m13.788 0c3.808 3.808 3.808 9.98 0 13.788" />
        </svg>
      ),
      color: isConnected ? "text-emerald-400" : "text-red-400",
      bgColor: isConnected ? "bg-emerald-500/10" : "bg-red-500/10",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="glass-card p-4 flex items-center gap-4">
          <div className={`p-2.5 rounded-lg ${card.bgColor}`}>
            <span className={card.color}>{card.icon}</span>
          </div>
          <div>
            <p className="text-xs text-surface-500 uppercase tracking-wider">{card.label}</p>
            <p className={`text-xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
