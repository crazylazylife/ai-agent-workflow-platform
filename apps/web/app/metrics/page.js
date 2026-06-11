"use client";
import { useEffect, useState } from "react";
import { getMetrics } from "../../lib/api";

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="muted">{sub}</div>}
    </div>
  );
}

export default function MetricsPage() {
  const [m, setM] = useState(null);
  const [err, setErr] = useState(null);

  async function refresh() {
    try { setM(await getMetrics()); setErr(null); }
    catch (e) { setErr(String(e)); }
  }
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  if (err) return <p className="error">{err}</p>;
  if (!m) return <p>Loading…</p>;

  const usd = (n) => `$${Number(n).toFixed(4)}`;
  return (
    <div>
      <h1>Metrics</h1>
      <div className="stat-grid">
        <Stat label="Total runs" value={m.runs.total} />
        <Stat label="Success rate" value={`${(m.runs.success_rate * 100).toFixed(0)}%`} sub="of terminal runs" />
        <Stat label="Total cost" value={usd(m.cost.total_usd)} sub={`${usd(m.cost.avg_per_run_usd)}/run`} />
        <Stat label="Tokens" value={m.tokens.total.toLocaleString()} sub={`${m.tokens.prompt} in / ${m.tokens.completion} out`} />
        <Stat label="Avg step latency" value={`${m.latency_ms.avg_step} ms`} sub={`p95 ${m.latency_ms.p95_step} ms`} />
        <Stat label="Tool failure rate" value={`${(m.tools.failure_rate * 100).toFixed(0)}%`} sub={`${m.tools.failures}/${m.tools.total_calls} calls`} />
        <Stat label="Retries" value={m.retries.total_attempts} sub={`${m.retries.steps_with_retries} steps retried`} />
      </div>

      <h2 style={{ fontSize: 16, marginTop: 24 }}>Runs by status</h2>
      <table>
        <thead><tr><th>Status</th><th>Count</th></tr></thead>
        <tbody>
          {Object.entries(m.runs.by_status).map(([s, c]) => (
            <tr key={s}><td>{s}</td><td>{c}</td></tr>
          ))}
          {m.runs.total === 0 && <tr><td colSpan={2} className="muted">No runs yet.</td></tr>}
        </tbody>
      </table>

      <h2 style={{ fontSize: 16, marginTop: 24 }}>Model usage</h2>
      <table>
        <thead><tr><th>Model</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead>
        <tbody>
          {m.models.map((x) => (
            <tr key={x.model}><td>{x.model}</td><td>{x.calls}</td><td>{x.tokens.toLocaleString()}</td><td>{usd(x.cost_usd)}</td></tr>
          ))}
          {m.models.length === 0 && <tr><td colSpan={4} className="muted">No model calls yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
