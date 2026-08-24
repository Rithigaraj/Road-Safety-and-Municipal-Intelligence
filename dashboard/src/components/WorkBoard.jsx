import React, { useRef, useState } from "react";
import { CLASS_LABELS } from "../api.js";

function SlaBadge({ order }) {
  if (order.status === "resolved") return null;
  if (order.sla_breached) return <span className="badge badge-breach">SLA breached</span>;
  const h = order.sla_remaining_hours;
  if (h == null) return null;
  const cls = h < 6 ? "badge-critical-sla" : h < 24 ? "badge-warn-sla" : "badge-ok-sla";
  return <span className={`badge ${cls}`}>{h >= 0 ? `${h}h left` : "overdue"}</span>;
}

export default function WorkBoard({ orders, onUpdate, onVerify, onEscalate, busy, user }) {
  const [tab, setTab] = useState("assigned");
  const fileRef = useRef(null);
  const [verifyFor, setVerifyFor] = useState(null);

  const tabs = ["assigned", "in_progress", "resolved"];
  const filtered = (orders ?? []).filter((o) => o.status === tab);
  const priority = (a, b) => (b.detection?.priority_score ?? 0) - (a.detection?.priority_score ?? 0);
  const canEscalate = user && (user.role === "admin" || user.role === "supervisor");

  const startVerify = (o) => {
    setVerifyFor(o);
    setTimeout(() => fileRef.current?.click(), 0);
  };

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !verifyFor) return;
    try {
      await onVerify(verifyFor.id, file);
      setTab("resolved");
    } catch (err) {
      alert(`Verification failed: ${err.message}`);
    } finally {
      setVerifyFor(null);
    }
  };

  return (
    <div className="card">
      <div className="card-head-row">
        <h3>Work tracking</h3>
        <span className="muted small">
          {orders?.filter((o) => o.sla_breached).length ?? 0} breached ·{" "}
          {orders?.filter((o) => o.detection?.is_duplicate).length ?? 0} duplicate reports merged
        </span>
      </div>
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t.replace("_", " ")}
            <span className="tab-count">{(orders ?? []).filter((o) => o.status === t).length}</span>
          </button>
        ))}
      </div>
      <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={onFile} />

      <table className="board">
        <thead>
          <tr>
            <th>#</th>
            <th>Problem</th>
            <th>Severity / size</th>
            <th>Priority</th>
            <th>Department</th>
            <th>Costs</th>
            <th>Assignee / notes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {[...filtered].sort(priority).map((o) => {
            const d = o.detection ?? {};
            return (
              <tr key={o.id}>
                <td>
                  {o.id}
                  {(d.report_count ?? 1) > 1 && (
                    <span className="dup-count" title="citizens reporting the same issue">×{d.report_count}</span>
                  )}
                </td>
                <td>
                  {CLASS_LABELS[d.class_name] ?? d.class_name}
                  {d.is_duplicate && <span className="badge badge-dup">dup</span>}
                  {o.verification_status === "verified" && <span className="badge badge-verified">AI ✓</span>}
                  {o.verification_status === "pending" && <span className="badge badge-pending">verify…</span>}
                  {o.verification_status === "failed" && <span className="badge badge-failed">fix rejected</span>}
                  {o.escalated_at && <span className="badge badge-escalated">escalated</span>}
                  <div><SlaBadge order={o} /></div>
                </td>
                <td>
                  {d.severity}
                  {d.size_estimate_cm != null && (
                    <span className="muted small"> · ~{Math.round(d.size_estimate_cm)}cm</span>
                  )}
                </td>
                <td>{d.priority_level}</td>
                <td>{(d.department_code ?? "").replaceAll("_", " ")}</td>
                <td className="small">
                  {o.estimated_cost != null ? `est ₹${o.estimated_cost.toLocaleString()}` : "—"}
                  {o.actual_cost != null && <div className="muted">act ₹{o.actual_cost.toLocaleString()}</div>}
                </td>
                <td className="small muted">
                  {o.assignee ?? "—"}
                  {o.notes ? ` · ${o.notes.slice(0, 40)}` : ""}
                </td>
                <td>
                  <div className="row-actions">
                    {o.status === "assigned" && (
                      <button className="btn" disabled={busy}
                              onClick={() => onUpdate(o.id, { status: "in_progress" })}>Start</button>
                    )}
                    {o.status === "in_progress" && (
                      <>
                        <button className="btn btn-primary" disabled={busy}
                                onClick={() =>
                                  onUpdate(o.id, {
                                    status: "resolved",
                                    actual_cost: o.estimated_cost ?? undefined,
                                  })
                                }>Mark resolved</button>
                        <button className="btn btn-cost" disabled={busy}
                                title="record actual spend"
                                onClick={() => {
                                  const v = window.prompt("Actual cost (₹):", String(o.estimated_cost ?? ""));
                                  if (v !== null) onUpdate(o.id, { actual_cost: parseFloat(v) || 0 });
                                }}>₹</button>
                      </>
                    )}
                    {o.status !== "resolved" && canEscalate && !o.sla_breached && (
                      <button className="btn btn-warn" disabled={busy} title="raise priority"
                              onClick={() => onEscalate(o.id)}>Escalate</button>
                    )}
                    {o.status === "resolved" && o.verification_status !== "verified" && (
                      <button className="btn" disabled={busy} onClick={() => startVerify(o)}>Verify with AI</button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
          {filtered.length === 0 && (
            <tr><td colSpan={8} className="muted">No orders in this state.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
