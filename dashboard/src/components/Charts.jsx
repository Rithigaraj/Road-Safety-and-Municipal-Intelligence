import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { CLASS_LABELS, PRIORITY_ORDER, SEVERITY_COLORS } from "../api.js";

const CLASS_COLORS = {
  pothole: "#ef4444",
  road_crack: "#b91c1c",
  garbage: "#10b981",
  broken_streetlight: "#f59e0b",
  water_leakage: "#3b82f6",
  damaged_traffic_sign: "#8b5cf6",
  blocked_drainage: "#06b6d4",
};

const SEVERITY_COLORS_ARR = [
  { key: "critical", color: "#dc2626" },
  { key: "high", color: "#ea580c" },
  { key: "medium", color: "#f59e0b" },
  { key: "low", color: "#16a34a" },
];

const PRIORITY_COLORS = { P1: "#dc2626", P2: "#f97316", P3: "#eab308", P4: "#64748b" };

export default function Charts({ stats }) {
  const byClass = (stats?.by_class ?? []).map((c) => ({
    name: CLASS_LABELS[c.class_name] ?? c.class_name,
    count: c.count,
    fill: CLASS_COLORS[c.class_name] ?? "#94a3b8",
  }));

  const bySeverity = (stats?.by_severity ?? []).map((s) => ({
    name: s.severity,
    value: s.count,
  }));

  const byPriority = PRIORITY_ORDER.map((p) => ({
    name: p,
    count: (stats?.by_priority ?? []).find((x) => x.level === p)?.count ?? 0,
    fill: PRIORITY_COLORS[p],
  }));

  const byDept = (stats?.by_department ?? []).map((d) => ({
    name: d.department.replaceAll("_", " "),
    count: d.count,
    fill: "#475569",
  }));

  return (
    <div className="charts-grid">
      <div className="card">
        <h3>Detections by problem type</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={byClass} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {byClass.map((e, i) => <Cell key={i} fill={e.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3>Severity distribution</h3>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie data={bySeverity} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} label={(p) => `${p.name} ${p.value}`}>
              {bySeverity.map((e, i) => (
                <Cell key={i} fill={SEVERITY_COLORS[e.name] ?? SEVERITY_COLORS_ARR[i]?.color ?? "#94a3b8"} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3>Priority queue</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={byPriority} layout="vertical" margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {byPriority.map((e, i) => <Cell key={i} fill={e.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3>Detections by department</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={byDept} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={120} />
            <Tooltip />
            <Bar dataKey="count" fill="#475569" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
