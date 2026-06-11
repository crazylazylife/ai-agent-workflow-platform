// Tiny typed-ish API client for the FastAPI backend.
const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function j(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...opts,
  });
  if (!res.ok) throw new Error(`${opts.method || "GET"} ${path} -> ${res.status}`);
  return res.status === 204 ? null : res.json();
}

export const listRuns = () => j("/runs");
export const getRun = (id) => j(`/runs/${id}`);
export const createRun = (task, model) =>
  j("/runs", { method: "POST", body: JSON.stringify({ task, model }) });

export const getModels = () => j("/models");

export const getMetrics = () => j("/metrics/summary");
export const getEvals = () => j("/evals/summary");

export const listPendingApprovals = () => j("/approvals?status=PENDING");
export const decideApproval = (id, decision, note = null) =>
  j(`/approvals/${id}/decide`, {
    method: "POST",
    body: JSON.stringify({ decision, decided_by: "operator", note }),
  });
