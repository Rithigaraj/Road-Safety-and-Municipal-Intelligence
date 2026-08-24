import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken } from "./api.js";
import StatCards from "./components/StatCards.jsx";
import Charts from "./components/Charts.jsx";
import MapView from "./components/MapView.jsx";
import PriorityQueue from "./components/PriorityQueue.jsx";
import WorkBoard from "./components/WorkBoard.jsx";
import SubmitComplaint from "./components/SubmitComplaint.jsx";
import LoginBar from "./components/LoginBar.jsx";
import Notifications from "./components/Notifications.jsx";
import ReportsPanel from "./components/ReportsPanel.jsx";
import DispatchPanel from "./components/DispatchPanel.jsx";

const TABS = [
  { id: "operations", label: "Operations" },
  { id: "reports", label: "City reports" },
  { id: "dispatch", label: "Dispatch" },
];

export default function App() {
  const [tab, setTab] = useState("operations");
  const [stats, setStats] = useState(null);
  const [heat, setHeat] = useState([]);
  const [orders, setOrders] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [user, setUser] = useState(null);
  const [notifTick, setNotifTick] = useState(0);
  const wsRef = useRef(null);

  // restore session on load
  useEffect(() => {
    if (getToken()) api.me().then(setUser).catch(() => api.logout());
  }, []);

  const load = useCallback(async () => {
    try {
      const [s, h, o] = await Promise.all([api.stats(), api.heatmap(), api.workOrders()]);
      setStats(s);
      setHeat(h);
      setOrders(o);
      setError("");
    } catch (err) {
      setError(`Backend unreachable: ${err.message}`);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  // live updates over websocket
  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let ws;
    let retry;
    const connect = () => {
      try {
        ws = new WebSocket(`${proto}://${location.host}/ws`);
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (["new_complaint", "work_order_updated", "verification"].includes(msg.event)) {
              load();
              setNotifTick((n) => n + 1);
            }
          } catch { /* ignore malformed frames */ }
        };
        ws.onclose = () => { retry = setTimeout(connect, 5000); };
      } catch { /* ws unsupported */ }
    };
    connect();
    return () => {
      clearTimeout(retry);
      ws?.close();
    };
  }, [load]);

  const updateOrder = async (id, body) => {
    setBusy(true);
    try {
      await api.updateWorkOrder(id, body);
      await load();
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const escalateOrder = async (id) => {
    setBusy(true);
    try {
      await api.escalateWorkOrder(id);
      await load();
      setNotifTick((n) => n + 1);
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const verifyOrder = async (id, file) => {
    setBusy(true);
    try {
      const w = await api.verifyWorkOrder(id, file);
      alert(`AI verification: ${w.verification_status.toUpperCase()}\n${w.verification_note}`);
      await load();
    } catch (err) {
      throw err;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Municipal Intelligence Platform</h1>
          <p className="muted">AI-powered road safety &amp; infrastructure management</p>
        </div>
        <div className="header-actions">
          <Notifications refreshKey={notifTick} />
          <LoginBar user={user} onUser={setUser} />
          <SubmitComplaint onSubmitted={() => { load(); setNotifTick((n) => n + 1); }} />
        </div>
      </header>

      {error && <div className="error banner">{error}</div>}

      <nav className="main-tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "operations" && (
          <>
            <StatCards stats={stats} orders={orders} />
            <div className="layout-2col">
              <div className="card">
                <h3>Live incident map</h3>
                <MapView points={heat} />
              </div>
              <PriorityQueue orders={orders} />
            </div>
            <Charts stats={stats} />
            <WorkBoard
              orders={orders}
              onUpdate={updateOrder}
              onVerify={verifyOrder}
              onEscalate={escalateOrder}
              busy={busy}
              user={user}
            />
          </>
        )}

        {tab === "reports" && <ReportsPanel />}

        {tab === "dispatch" && (
          <>
            <DispatchPanel user={user} />
            <div className="card">
              <h3>Bulk exports</h3>
              <p className="muted small">CSV downloads for records / RTI use.</p>
              <div className="row-actions">
                <a className="btn" href="/api/export/work-orders.csv" target="_blank" rel="noreferrer">
                  ⬇ work orders CSV
                </a>
                <a className="btn" href="/api/export/complaints.csv" target="_blank" rel="noreferrer">
                  ⬇ complaints CSV
                </a>
                {user?.role === "admin" && (
                  <button className="btn btn-warn" onClick={() => api.slaScan().then((r) =>
                    alert(`SLA scan complete: ${r.newly_breached.length} new breaches flagged`))}>
                    Run SLA scan now
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </main>

      <footer className="muted small">
        Pipeline: image → detection → severity → priority → department → SLA tracking → AI verification
        · duplicates merged automatically · live via websocket
      </footer>
    </div>
  );
}
