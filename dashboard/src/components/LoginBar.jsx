import React, { useState } from "react";
import { api, getToken } from "../api.js";

export default function LoginBar({ user, onUser }) {
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(username, password);
      const me = await api.me();
      onUser(me);
      setOpen(false);
      setPassword("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!getToken()) {
    return (
      <div className="login-area">
        {open ? (
          <form className="login-form" onSubmit={submit}>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" autoFocus />
            <button className="btn btn-primary" disabled={busy}>{busy ? "…" : "Sign in"}</button>
            {error && <span className="login-error">{error}</span>}
          </form>
        ) : (
          <button className="btn" onClick={() => setOpen(true)}>Staff sign in</button>
        )}
        <span className="muted small">demo: admin / admin123</span>
      </div>
    );
  }

  return (
    <div className="login-area">
      <span className={`badge badge-role role-${user?.role ?? "crew"}`}>
        {user ? `${user.username} · ${user.role}` : "staff"}
      </span>
      <button
        className="btn"
        onClick={() => {
          api.logout();
          onUser(null);
        }}
      >
        Sign out
      </button>
    </div>
  );
}
