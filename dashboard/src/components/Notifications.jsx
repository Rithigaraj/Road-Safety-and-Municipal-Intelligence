import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const TYPE_ICONS = {
  new_complaint: "📸",
  sla_breach: "⏰",
  escalation: "🚨",
  verification: "🔍",
};

export default function Notifications({ refreshKey, onGotoWork }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const boxRef = useRef(null);

  const load = async () => {
    try {
      const [list, count] = await Promise.all([api.notifications(), api.unreadCount()]);
      setItems(list);
      setUnread(count.count);
    } catch {
      /* backend not ready */
    }
  };

  useEffect(() => { load(); }, [refreshKey]);

  useEffect(() => {
    const close = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div className="notif-area" ref={boxRef}>
      <button className="bell" onClick={() => setOpen((o) => !o)} title="Notifications">
        🔔
        {unread > 0 && <span className="bell-badge">{unread > 99 ? "99+" : unread}</span>}
      </button>

      {open && (
        <div className="notif-panel">
          <div className="notif-head">
            <strong>Notifications</strong>
            <button
              className="btn btn-sm"
              onClick={async () => {
                await api.markAllRead();
                load();
              }}
            >
              Mark all read
            </button>
          </div>
          <div className="notif-list">
            {items.length === 0 && <div className="muted small pad">Nothing yet.</div>}
            {items.map((n) => (
              <div
                key={n.id}
                className={`notif-item ${n.read ? "read" : "unread"}`}
                onClick={async () => {
                  if (!n.read) {
                    await api.markRead(n.id).catch(() => {});
                    load();
                  }
                  if (n.ref_type === "work_order") onGotoWork?.();
                }}
              >
                <span className="notif-icon">{TYPE_ICONS[n.type] ?? "•"}</span>
                <span>
                  <div className="notif-title">{n.title}</div>
                  {n.body && <div className="muted small">{n.body}</div>}
                  <div className="muted small">{new Date(n.created_at).toLocaleString()}</div>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
