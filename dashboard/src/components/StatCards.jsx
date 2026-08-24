import React from "react";

export default function StatCards({ stats, orders }) {
  const breached = (orders ?? []).filter((o) => o.sla_breached).length;
  const cards = [
    { label: "Open work orders", value: stats?.open_work ?? "-", sub: `${stats?.total_complaints ?? 0} complaints`, color: "#3b82f6", icon: "🛠️" },
    { label: "Critical severity", value: stats?.by_severity?.find((s) => s.severity === "critical")?.count ?? 0, sub: "needs immediate action", color: "#dc2626", icon: "⚠️" },
    { label: "Resolved", value: stats?.resolved ?? 0, sub: `${stats?.verified ?? 0} AI-verified`, color: "#16a34a", icon: "✅" },
    { label: "SLA compliance", value: stats ? `${Math.round((stats.sla_compliance ?? 1) * 100)}%` : "-", sub: "resolved within SLA", color: "#f59e0b", icon: "⏱️" },
    { label: "SLA breaches open", value: breached, sub: "escalate or dispatch now", color: breached ? "#dc2626" : "#16a34a", icon: "🚨" },
    { label: "Budget estimate", value: stats ? `₹${Math.round(stats.budget?.estimated_total ?? 0).toLocaleString()}` : "-", sub: `spent ₹${Math.round(stats?.budget?.actual_total ?? 0).toLocaleString()}`, color: "#8b5cf6", icon: "💰" },
  ];
  return (
    <div className="stat-grid">
      {cards.map((c) => (
        <div className="stat-card" key={c.label} style={{ borderLeft: `4px solid ${c.color}` }}>
          <div className="stat-icon">{c.icon}</div>
          <div>
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
            <div className="stat-sub">{c.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
