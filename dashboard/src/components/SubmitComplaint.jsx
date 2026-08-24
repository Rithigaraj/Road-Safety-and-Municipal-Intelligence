import React, { useRef, useState } from "react";
import { api, CLASS_LABELS, SEVERITY_COLORS } from "../api.js";

export default function SubmitComplaint({ onSubmitted }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [preview, setPreview] = useState(null);
  const fileRef = useRef(null);
  const [form, setForm] = useState({
    source: "citizen",
    description: "",
    address: "",
    lat: "",
    lon: "",
  });

  const reset = () => {
    setForm({ source: "citizen", description: "", address: "", lat: "", lon: "" });
    setPreview(null);
    setResult(null);
    setError("");
  };

  const onPick = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPreview(URL.createObjectURL(f));
    fileRef.current = f;
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!fileRef.current) {
      setError("Please choose an image.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const complaint = await api.submitComplaint({
        ...form,
        lat: form.lat === "" ? null : parseFloat(form.lat),
        lon: form.lon === "" ? null : parseFloat(form.lon),
        file: fileRef.current,
      });
      setResult(complaint);
      onSubmitted?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    setOpen(false);
    reset();
  };

  return (
    <>
      <button className="btn btn-primary btn-lg" onClick={() => setOpen(true)}>
        + Report a problem
      </button>

      {open && (
        <div className="modal-backdrop" onClick={close}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>{result ? "Analysis result" : "Report a municipal problem"}</h2>
              <button className="modal-close" onClick={close}>×</button>
            </div>

            {result ? (
              <div>
                <div className="tracking-banner">
                  <span className="muted">Tracking code</span>
                  <strong className="tracking-code">{result.tracking_code}</strong>
                  <span className="muted small">
                    {result.detections.some((d) => d.is_duplicate)
                      ? "· matched an existing open issue (merged, no duplicate crew sent)"
                      : "· save this to check status later"}
                  </span>
                </div>
                <table className="board">
                  <thead>
                    <tr><th>Problem</th><th>Confidence</th><th>Severity</th><th>Priority</th><th>Department</th></tr>
                  </thead>
                  <tbody>
                    {result.detections.map((d) => (
                      <tr key={d.id}>
                        <td>{CLASS_LABELS[d.class_name] ?? d.class_name}</td>
                        <td>{Math.round(d.confidence * 100)}%</td>
                        <td style={{ color: SEVERITY_COLORS[d.severity] }}>{d.severity}</td>
                        <td>{d.priority_level} (SLA {d.sla_hours}h)</td>
                        <td>{d.department_code.replaceAll("_", " ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button className="btn btn-primary" onClick={close}>Done</button>
              </div>
            ) : (
              <form onSubmit={submit}>
                <div className="form-row">
                  <label className="form-label">Photo</label>
                  <div className="drop" onClick={() => document.getElementById("photo-input")?.click()}>
                    {preview ? <img src={preview} alt="preview" /> : "Click to choose an image"}
                  </div>
                  <input id="photo-input" type="file" accept="image/*" style={{ display: "none" }} onChange={onPick} />
                </div>

                <div className="form-row">
                  <label className="form-label">Source</label>
                  <select value={form.source} onChange={set("source")}>
                    <option value="citizen">Citizen report</option>
                    <option value="cctv">CCTV camera</option>
                    <option value="dashcam">Dashcam feed</option>
                  </select>
                </div>

                <div className="form-row">
                  <label className="form-label">Description</label>
                  <textarea rows="2" value={form.description} onChange={set("description")} placeholder="What did you see?" />
                </div>

                <div className="form-row">
                  <label className="form-label">Location</label>
                  <div className="form-cols">
                    <input type="text" placeholder="Address" value={form.address} onChange={set("address")} />
                    <input type="number" step="any" placeholder="Latitude (optional)" value={form.lat} onChange={set("lat")} />
                    <input type="number" step="any" placeholder="Longitude (optional)" value={form.lon} onChange={set("lon")} />
                  </div>
                  <span className="muted small">Leave coordinates empty — phone photos carry GPS automatically.</span>
                </div>

                {error && <div className="error">{error}</div>}
                <div className="form-actions">
                  <button type="button" className="btn" onClick={close}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={busy}>
                    {busy ? "Analyzing…" : "Submit & analyze"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
