import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Page } from "../../api/types";
import { when } from "../../components/Badges";

interface LineItem {
  service: string;
  usage: number;
  unit: string;
  rate_usd: number;
  cost_usd: number;
}
interface Estimate {
  period: { from: string; to: string; hours: number };
  provider: string;
  line_items: LineItem[];
  total_usd: number;
  requests: number;
  orders: number;
  cost_per_1000_orders_usd: number | null;
  assumptions: string[];
}
interface Run {
  id: number;
  scenario: string;
  status: string;
  started_at: string;
  estimated_cost_usd: number | null;
  total_requests: number | null;
}
interface Report {
  id: number;
  report_type: "LOAD_TEST" | "COST" | "COMPARISON";
  load_test_run_id: number | null;
  s3_key: string;
  format: string;
  created_at: string;
}

const usd = (v: number | null, d = 4) => (v === null || v === undefined ? "—" : `$${v.toFixed(d)}`);
const PERIODS: Record<string, number> = { "Last hour": 1, "Last 3 hours": 3, "Last 24 hours": 24 };

export default function Costs() {
  const [period, setPeriod] = useState("Last hour");
  const [runId, setRunId] = useState("");
  const [est, setEst] = useState<Estimate | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [fmt, setFmt] = useState("MD");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const loadLists = useCallback(async () => {
    try {
      const [r, rep] = await Promise.all([
        api<Page<Run>>("/admin/load-tests?page_size=50"),
        api<Page<Report>>("/admin/reports?page_size=20"),
      ]);
      setRuns(r.items);
      setReports(rep.items);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const loadEstimate = useCallback(async () => {
    try {
      if (runId) {
        setEst(await api<Estimate>(`/admin/costs/estimate?run_id=${runId}`));
      } else {
        const to = new Date();
        const from = new Date(to.getTime() - PERIODS[period] * 3600_000);
        setEst(await api<Estimate>(`/admin/costs/estimate?from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`));
      }
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [period, runId]);

  useEffect(() => {
    loadLists();
  }, [loadLists]);
  useEffect(() => {
    loadEstimate();
  }, [loadEstimate]);

  async function generate(body: Record<string, unknown>) {
    setMsg("");
    try {
      const r = await api<{ report_id: number }>("/admin/reports", { method: "POST", body: { ...body, format: fmt } });
      setMsg(`Report #${r.report_id} created.`);
      setError("");
      loadLists();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function download(id: number) {
    try {
      const d = await api<{ url: string }>(`/admin/reports/${id}/download`);
      window.open(d.url, "_blank");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const finished = runs.filter((r) => r.status !== "RUNNING");

  return (
    <section>
      <h1>Costs & reports</h1>
      {error && <p className="error">{error}</p>}
      <p className="muted">
        Estimates = published on-demand AWS rates × measured usage (Cost Explorer is not available in the Learner Lab).
      </p>

      <div className="row">
        <select value={runId ? "" : period} disabled={!!runId} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
          {Object.keys(PERIODS).map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <select value={runId} onChange={(e) => setRunId(e.target.value)} aria-label="Load test run">
          <option value="">or a load-test run…</option>
          {finished.map((r) => (
            <option key={r.id} value={r.id}>
              Run #{r.id} · {r.scenario} · {when(r.started_at)}
            </option>
          ))}
        </select>
        <button className="btn small" onClick={loadEstimate}>
          Refresh
        </button>
      </div>

      {est && (
        <>
          <div className="stats">
            <div className="card"><span className="muted">Estimated total</span><strong>{usd(est.total_usd)}</strong></div>
            <div className="card"><span className="muted">Period</span><strong>{est.period.hours.toFixed(2)} h</strong></div>
            <div className="card"><span className="muted">Requests</span><strong>{est.requests}</strong></div>
            <div className="card"><span className="muted">Orders</span><strong>{est.orders}</strong></div>
            <div className="card"><span className="muted">Per 1,000 orders</span><strong>{usd(est.cost_per_1000_orders_usd)}</strong></div>
          </div>
          <table className="table">
            <thead><tr><th>Service</th><th>Usage</th><th>Unit</th><th>Rate</th><th>Cost</th></tr></thead>
            <tbody>
              {est.line_items.map((i) => (
                <tr key={i.service}>
                  <td>{i.service}</td>
                  <td>{i.usage.toFixed(4)}</td>
                  <td>{i.unit}</td>
                  <td>{usd(i.rate_usd, 4)}</td>
                  <td>{usd(i.cost_usd, 5)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <details>
            <summary className="muted">Assumptions</summary>
            <ul>{est.assumptions.map((a) => <li key={a} className="muted">{a}</li>)}</ul>
          </details>
        </>
      )}

      <h2>Reports</h2>
      <div className="row">
        <select value={fmt} onChange={(e) => setFmt(e.target.value)} aria-label="Format">
          <option value="MD">Markdown</option>
          <option value="CSV">CSV</option>
          <option value="JSON">JSON</option>
        </select>
        <button className="btn primary" onClick={() => generate({ report_type: "COMPARISON" })}>
          Normal vs Festival comparison
        </button>
        <button
          className="btn"
          onClick={() => {
            const to = new Date();
            const from = new Date(to.getTime() - PERIODS[period] * 3600_000);
            generate(runId ? { report_type: "LOAD_TEST", run_ids: [Number(runId)] } : { report_type: "COST", from: from.toISOString(), to: to.toISOString() });
          }}
        >
          {runId ? "Report for selected run" : "Cost report for period"}
        </button>
      </div>
      {msg && <p className="success">{msg}</p>}
      {reports.length === 0 ? (
        <p className="muted">No reports yet.</p>
      ) : (
        <table className="table">
          <thead><tr><th>#</th><th>Type</th><th>Format</th><th>Run</th><th>Created</th><th /></tr></thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.report_type}</td>
                <td>{r.format}</td>
                <td>{r.load_test_run_id ?? "—"}</td>
                <td>{when(r.created_at)}</td>
                <td><button className="btn small" onClick={() => download(r.id)}>Download</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
