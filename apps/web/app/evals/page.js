"use client";
import { useEffect, useState } from "react";
import { getEvals } from "../../lib/api";

function Check({ name, ok }) {
  return (
    <span className="badge" style={{ background: ok ? "#16a34a" : "#dc2626", marginRight: 4 }}>
      {ok ? "✓" : "✗"} {name}
    </span>
  );
}

export default function EvalsPage() {
  const [e, setE] = useState(null);
  const [err, setErr] = useState(null);

  async function refresh() {
    try { setE(await getEvals()); setErr(null); }
    catch (x) { setErr(String(x)); }
  }
  useEffect(() => { refresh(); const t = setInterval(refresh, 5000); return () => clearInterval(t); }, []);

  if (err) return <p className="error">{err}</p>;
  if (!e) return <p>Loading…</p>;
  if (e.total === 0) return <div><h1>Evals</h1><p className="muted">No eval results yet. Run <code>python packages/evals/runner.py</code> with the stack up.</p></div>;

  return (
    <div>
      <h1>Eval results</h1>
      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">{(e.pass_rate * 100).toFixed(0)}%</div>
          <div className="stat-label">Pass rate</div>
          <div className="muted">{e.passed}/{e.total} tasks</div>
        </div>
        {Object.entries(e.by_category).map(([c, v]) => (
          <div className="stat" key={c}>
            <div className="stat-value">{v.passed}/{v.total}</div>
            <div className="stat-label">{c}</div>
          </div>
        ))}
      </div>

      <h2 style={{ fontSize: 16, marginTop: 24 }}>Tasks</h2>
      <table>
        <thead>
          <tr><th>Task</th><th>Result</th><th>Score</th><th>Cost</th><th>Checks</th></tr>
        </thead>
        <tbody>
          {e.tasks.map((t) => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>
                <span className="badge" style={{ background: t.passed ? "#16a34a" : "#dc2626" }}>
                  {t.passed ? "PASS" : "FAIL"}
                </span>
              </td>
              <td>{(t.score * 100).toFixed(0)}%</td>
              <td>${Number(t.cost_usd).toFixed(4)}</td>
              <td>{Object.entries(t.checks || {}).map(([k, v]) => <Check key={k} name={k} ok={v} />)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
