"use client";
import { useEffect, useState } from "react";
import { listPendingApprovals, decideApproval } from "../../lib/api";

export default function ApprovalsPage() {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  async function refresh() {
    try {
      setItems(await listPendingApprovals());
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  async function decide(id, decision) {
    setBusy(id);
    try {
      await decideApproval(id, decision);
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <h1>Pending Approvals</h1>
      {err && <p className="error">{err}</p>}
      {items.length === 0 && <p className="muted">Nothing waiting for approval. 🎉</p>}
      {items.map((a) => (
        <div key={a.id} className="card">
          <div className="card-task">{a.task || "(no task text)"}</div>
          <div className="muted">Agent recommendation:</div>
          <pre>{JSON.stringify(a.recommendation, null, 2)}</pre>
          <div className="row">
            <button className="approve" disabled={busy === a.id} onClick={() => decide(a.id, "approve")}>
              Approve
            </button>
            <button className="reject" disabled={busy === a.id} onClick={() => decide(a.id, "reject")}>
              Reject
            </button>
            <a href={`/runs/${a.run_id}`}>view run</a>
          </div>
        </div>
      ))}
    </div>
  );
}
