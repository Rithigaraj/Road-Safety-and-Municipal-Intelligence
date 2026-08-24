import React, { useEffect, useState } from "react";
import { api, CLASS_LABELS } from "../api.js";

function healthColor(idx) {
  if (idx >= 80) return "#16a34a";
  if (idx >= 55) return "#f59e0b";
  if (idx >= 30) return "#ea580c";
  return "#dc2626";
}

export default function ReportsPanel() {
  const [streets, setStreets] = useState([]);
  const [zones, setZones] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [trends, setTrends] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, z, f, t] = await Promise.all([
          api.streets(), api.zones(), api.forecast(), api.trends(30),
        ]);
        setStreets(s);
        setZones(z);
        setForecast(f);
        setTrends(t);
      } catch {
        /* ignore */
      }
    })();
  }, []);

  const maxCount = Math.max(...trends?.detections_per_day?.map((d) => d.count) ?? [1], 1);

  return (
    <div className="reports-grid">
      <div className="card">
        <h3>Street health index</h3>
        <p className="muted small">0 = crumbling, 100 = pristine. Driven by open issues and their severity.</p>
        <div className="street-list">
          {streets.slice(0, 8).map((s) => (
            <div key={s.address} className="street-row">
              <span className="street-name">{s.address}</span>
              <div className="street-bar">
                <div style={{ width: `${s.health_index}%`, background: healthColor(s.health_index) }} />
              </div>
              <span className="street-score" style={{ color: healthColor(s.health_index) }}>
                {s.health_index}
              </span>
            </div>
          ))}
          {streets.length === 0 && <div className="muted small">No geocoded issues yet.</div>}
        </div>
      </div>

      <div className="card">
        <h3>Hotspot zones</h3>
        <p className="muted small">Grid cells ranked by incident load (severity-weighted).</p>
        <table className="board">
          <thead><tr><th>#</th><th>Lat range</th><th>Lon range</th><th>Reports</th><th>Load</th></tr></thead>
          <tbody>
            {zones.slice(0, 6).map((z, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td>{z.lat_min.toFixed(4)}–{z.lat_max.toFixed(4)}</td>
                <td>{z.lon_min.toFixed(4)}–{z.lon_max.toFixed(4)}</td>
                <td>{z.count}</td>
                <td>
                  <div className="zone-load">
                    <div style={{ width: `${Math.round(z.intensity * 100)}%` }} />
                  </div>
                </td>
              </tr>
            ))}
            {zones.length === 0 && (
              <tr><td colSpan={5} className="muted">No mapped incidents yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Next-7-day forecast</h3>
        <p className="muted small">Moving average with trend factor over the last four weeks.</p>
        <table className="board">
          <thead><tr><th>Problem</th><th>Last week</th><th>Trend</th><th>Predicted</th></tr></thead>
          <tbody>
            {(forecast?.per_class ?? []).slice(0, 7).map((p) => (
              <tr key={p.class_name}>
                <td>{CLASS_LABELS[p.class_name] ?? p.class_name}</td>
                <td>{p.last_week_count}</td>
                <td>{p.trend >= 1.05 ? "▲" : p.trend <= 0.95 ? "▼" : "—"} {p.trend}×</td>
                <td><strong>{p.predicted_next_week}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Reports per day (30d)</h3>
        {trends ? (
          <div className="spark-row">
            {trends.detections_per_day.map((d) => (
              <div
                key={d.date}
                className="spark-bar"
                title={`${d.date}: ${d.count}`}
                style={{ height: `${Math.max(2, Math.round((d.count / maxCount) * 60))}px` }}
              />
            ))}
          </div>
        ) : (
          <div className="muted small">Loading…</div>
        )}
      </div>
    </div>
  );
}
