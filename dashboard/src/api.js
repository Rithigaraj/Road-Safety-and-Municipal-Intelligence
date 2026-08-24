const BASE = "";
const TOKEN_KEY = "rsm_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function req(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => req("/api/health"),
  stats: () => req("/api/dashboard/stats"),
  heatmap: () => req("/api/reports/heatmap"),
  complaints: () => req("/api/complaints"),
  workOrders: (status) => req(`/api/work-orders${status ? `?status=${status}` : ""}`),
  departments: () => req("/api/departments"),

  streets: () => req("/api/reports/streets"),
  zones: () => req("/api/reports/zones"),
  trends: (days = 30) => req(`/api/reports/trends?days=${days}`),
  forecast: () => req("/api/reports/forecast"),

  dispatchRoute: (department) =>
    req(`/api/dispatch/route${department ? `?department=${department}` : ""}`),

  notifications: () => req("/api/notifications"),
  unreadCount: () => req("/api/notifications/unread-count"),
  markRead: (id) => req(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => req("/api/notifications/read-all", { method: "POST" }),
  slaScan: () => req("/api/notifications/sla-scan", { method: "POST" }),

  login: async (username, password) => {
    const out = await req("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    setToken(out.access_token);
    return out;
  },
  logout: () => setToken(""),
  me: () => req("/api/auth/me"),

  updateWorkOrder: (id, body) =>
    req(`/api/work-orders/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  escalateWorkOrder: (id) =>
    req(`/api/work-orders/${id}/escalate`, { method: "POST" }),

  verifyWorkOrder: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req(`/api/work-orders/${id}/verify`, { method: "POST", body: fd });
  },

  analyze: (file, lat, lon) => {
    const fd = new FormData();
    fd.append("file", file);
    if (lat != null) fd.append("lat", String(lat));
    if (lon != null) fd.append("lon", String(lon));
    return req("/api/complaints/analyze", { method: "POST", body: fd });
  },

  submitComplaint: ({ source, description, lat, lon, address, file }) => {
    const fd = new FormData();
    fd.append("source", source);
    fd.append("description", description || "");
    if (lat != null) fd.append("lat", String(lat));
    if (lon != null) fd.append("lon", String(lon));
    if (address) fd.append("address", address);
    fd.append("file", file);
    return req("/api/complaints", { method: "POST", body: fd });
  },

  submitVideo: ({ source, lat, lon, address, file, frames }) => {
    const fd = new FormData();
    fd.append("source", source || "cctv");
    if (lat != null) fd.append("lat", String(lat));
    if (lon != null) fd.append("lon", String(lon));
    if (address) fd.append("address", address);
    if (frames) fd.append("frames_to_sample", String(frames));
    fd.append("file", file);
    return req("/api/complaints/video", { method: "POST", body: fd });
  },

  exportUrl: (name) => `${BASE}/api/export/${name}${getToken() ? "" : ""}`,
};

export const CLASS_LABELS = {
  pothole: "Pothole",
  road_crack: "Road crack",
  garbage: "Garbage",
  broken_streetlight: "Broken streetlight",
  water_leakage: "Water leakage",
  damaged_traffic_sign: "Damaged sign",
  blocked_drainage: "Blocked drainage",
};

export const SEVERITY_COLORS = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#f59e0b",
  low: "#16a34a",
};

export const PRIORITY_ORDER = ["P1", "P2", "P3", "P4"];
export const STATUS_LABELS = {
  assigned: "Assigned",
  in_progress: "In progress",
  resolved: "Resolved",
  pending: "Pending verification",
  verified: "AI verified",
  failed: "Verification failed",
};
