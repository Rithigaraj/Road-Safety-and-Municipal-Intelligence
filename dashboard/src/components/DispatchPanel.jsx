import React, { useCallback, useEffect, useState } from "react";
import { api, CLASS_LABELS } from "../api.js";

export default function DispatchPanel({ user }) {
  const [route, setRoute] = useState(null);
  const [department, setDepartment] = useState("");
  const [error, setError] = useState("");
  const canUse = !!user; // any signed-in staff role

  const load = useCallback(async (dept) => {
    if (!canUse) return;
    setError("");
    try {
      setRoute(await api.dispatchRoute(dept || undefined));
    } catch (err) {
      setError(err.message);
    }
  }, [canUse]);

  useEffect(() => { load(department); }, [load, department]);

  if (!canUse) {
    return (
      <div className="card">
        <h3>Crew dispatch route</h3>
        <p className="muted">Sign in as staff to generate optimised crew routes.</p>
      </div>
    );
  }

  let cumulative = 0;
  return (
    <div className="card">
      <div className="card-head-row">
        <h3>Crew dispatch route</h3>
        <select value={department} onChange={(e) => setDepartment(e.target.value)}>
          <option value="">All departments</option>
          <option value="road_maintenance">Road Maintenance</option>
          <option value="street_lighting">Street Lighting</option>
          <option value="waste_management">Waste Management</option>
          <option value="water_supply">Water Supply</option>
          <option value="drainage">Drainage</option>
          <option value="traffic_signage">Traffic &amp; Signage</option>
        </select>
      </div>

      {error && <div className="error">{error}</div>}

      {route && (
        <>
          <p className="muted small">
            {route.stops.length} stops · {route.total_km} km total ·
            greedy nearest-neighbour + 2-opt from the municipal depot.
          </p>
          <table className="board">
            <thead>
              <tr><th>#</th><th>+Leg</th><th>Total</th><th>Problem</th><th>Priority</th><th>Address</th></tr>
            </thead>
            <tbody>
              {route.stops.map((s, i) => {
                cumulative = Math.round((cumulative + s.leg_km) * 100) / 100;
                return (
                  <tr key={s.work_order_id}>
                    <td>{i + 1}</td>
                    <td>{s.leg_km} km</td>
                    <td>{cumulative} km</td>
                    <td>{CLASS_LABELS[s.class_name] ?? s.class_name}</td>
                    <td><span className={`badge badge-${s.priority_level.toLowerCase()}`}>{s.priority_level}</span></td>
                    <td>{s.address ?? "—"}</td>
                  </tr>
                );
              })}
              {route.stops.length === 0 && (
                <tr><td colSpan={6} className="muted">No open work orders to route.</td></tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
