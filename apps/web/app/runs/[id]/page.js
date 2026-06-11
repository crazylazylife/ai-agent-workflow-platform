"use client";
import { useEffect, useState } from "react";
import { getRun } from "../../../lib/api";

export default function RunDetail({ params }) {
  const { id } = params;
  const [run, setRun] = useState(null);
  const [err, setErr] = useState(null);

  async function refresh() {
    try {
      setRun(await getRun(id));
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [id]);

  if (err) return <p className="error">{err}</p>;
  if (!run) return <p>Loading…</p>;

  return (
    <div>
      <p><a href="/">← Runs</a></p>
      <h1>Run {id.slice(0, 8)}</h1>
      <p>Status: <strong>{run.status}</strong></p>
      <p className="muted">Task: {run.input?.task}</p>
      <table>
        <thead>
          <tr><th>#</th><th>Step</th><th>Type</th><th>Status</th></tr>
        </thead>
        <tbody>
          {run.steps.map((s, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>{s.name}</td>
              <td>{s.type}</td>
              <td>{s.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
