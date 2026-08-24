import React from "react";
import { CLASS_LABELS, SEVERITY_COLORS } from "../api.js";

export default function PriorityQueue({ orders }) {
  const open = (orders ?? []).filter((o) => o.status !== "resolved");
  const sorted = [...open].sort(
    (a, b) => (b.detection?.priority_score ?? 0) - (a.detection?.priority_score ?? 0)
  );
  const top = sorted.slice(0, 8);

  return (
    <div className="card">
      <h3>Priority queue <span className="muted">(open, by priority score)</span></h3>
      {top.length === 0 && <p className="muted">No open work orders.</p>}
      <ul className="queue">
        {top.map((o) => {
          const d = o.detection;
          return (
            <li key={o.id} className="queue-row">
              <span className={`pill pill-${d?.priority_level}`}>{d?.priority_level}</span>
              <div className="queue-main">
                <span className="queue-title">{CLASS_LABELS[d?.class_name] ?? d?.class_name}</span>
                <span className="muted small">
                  {d?.department_code.replaceAll("_", " ")} · #{o.id}
                </span>
              </div>
              <span className="sev" style={{ color: SEVERITY_COLORS[d?.severity] }}>
                {d?.severity}
              </span>
              <span className="score">{Math.round((d?.priority_score ?? 0) * 100)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
