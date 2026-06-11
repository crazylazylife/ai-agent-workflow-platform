"use client";
import { useEffect, useState } from "react";
import { listRuns, createRun, getModels } from "../lib/api";

const COLORS = {
  PENDING: "#888",
  RUNNING: "#2563eb",
  WAITING_FOR_APPROVAL: "#d97706",
  SUCCEEDED: "#16a34a",
  FAILED: "#dc2626",
  REJECTED: "#dc2626",
};

export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [task, setTask] = useState("");
  const [err, setErr] = useState(null);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");

  async function refresh() {
    try {
      setRuns(await listRuns());
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000); // poll for live status
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    getModels()
      .then((m) => { setModels(m.models || []); setModel(m.default || ""); })
      .catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (!task.trim()) return;
    await createRun(task.trim(), model || undefined);
    setTask("");
    refresh();
  }

  return (
    <div>
      <h1>Runs</h1>
      <form onSubmit={submit} className="row">
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Describe a task, e.g. 'Research 3 CRMs'…"
        />
        {models.length > 0 && (
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{ padding: 8, borderRadius: 6, border: "1px solid #ccc" }}
            title="Model for this run"
          >
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
        <button type="submit">Start run</button>
      </form>
      {err && <p className="error">{err}</p>}
      <table>
        <thead>
          <tr><th>Task</th><th>Status</th><th>Created</th><th></th></tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{r.task}</td>
              <td>
                <span className="badge" style={{ background: COLORS[r.status] || "#888" }}>
                  {r.status}
                </span>
              </td>
              <td>{new Date(r.created_at).toLocaleTimeString()}</td>
              <td><a href={`/runs/${r.id}`}>view</a></td>
            </tr>
          ))}
          {runs.length === 0 && (
            <tr><td colSpan={4} className="muted">No runs yet — start one above.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
