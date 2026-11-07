import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Page } from "../../api/types";
import { when } from "../../components/Badges";

interface Scenario {
  name: "NORMAL" | "FESTIVAL";
  description: string;
  users: number;
  spawn_rate: number;
  duration_s: number;
}

interface Run {
  id: number;
  scenario: string;
  status: "RUNNING" | "COMPLETED" | "STOPPED" | "FAILED";
  target_users: number;
  duration_seconds: number;
  started_at: string;
  ended_at: string | null;
  total_requests: number | null;
  failed_requests: number | null;
  avg_response_ms: number | null;
  p95_response_ms: number | null;
  peak_rps: number | null;
}

interface Live {
  users: number;
  rps: number;
  total_requests: number;
  failed_requests: number;
  avg_response_ms: number;
  p95_response_ms: number;
  elapsed_s: number;
  endpoints: { name: string; requests: number; failures: number; avg_ms: number; p95_ms: number | null }[];
}

const n = (v: number | null, d = 0) => (v === null || v === undefined ? "—" : v.toFixed(d));
const pct = (f: number | null, t: number | null) => (t ? `${((100 * (f ?? 0)) / t).toFixed(2)} %` : "—");

export default function LoadTests() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [active, setActive] = useState<Run | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [quick, setQuick] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const h = await api<Page<Run>>("/admin/load-tests?page_size=20");
      setRuns(h.items);
      const running = h.items.find((r) => r.status === "RUNNING");
      if (running) {
        const d = await api<{ run: Run; live_stats: Live | null }>(`/admin/load-tests/${running.id}`);
        setActive(d.run.status === "RUNNING" ? d.run : null);
        setLive(d.live_stats);
        if (d.run.status !== "RUNNING") {
          setRuns((await api<Page<Run>>("/admin/load-tests?page_size=20")).items);
        }
      } else {
        setActive(null);
        setLive(null);
      }
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    api<Scenario[]>("/admin/load-tests/scenarios").then(setScenarios).catch((e) => setError(e.message));
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  async function start(s: Scenario) {
    setBusy(true);
    try {
      // "Quick run" keeps local demos short: 60 s and a smaller crowd.
      const body = quick
        ? { scenario: s.name, duration_s: 60, users: Math.min(s.users, s.name === "FESTIVAL" ? 100 : 15) }
        : { scenario: s.name };
      await api("/admin/load-tests", { method: "POST", body });
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      refresh();
    }
  }

  async function stop() {
    if (!active) return;
    setBusy(true);
    try {
      await api(`/admin/load-tests/${active.id}/stop`, { method: "POST" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      refresh();
    }
  }

  return (
    <section>
      <h1>Load tests</h1>
      {error && <p className="error">{error}</p>}
      <p className="muted">
        Simulated customers (70 % Free / 30 % Premium) browse, order and view orders through Locust. Their orders
        appear in the queue like real ones.
      </p>

      <div className="grid">
        {scenarios.map((s) => (
          <article key={s.name} className="card item">
            <h3>{s.name === "FESTIVAL" ? "🎉 Festival day" : "☀ Normal day"}</h3>
            <p className="muted">{s.description}</p>
            <p>
              {s.users} users · {s.spawn_rate}/s spawn · {Math.round(s.duration_s / 60)} min
            </p>
            <button className="btn primary" disabled={busy || !!active} onClick={() => start(s)}>
              Start {s.name.toLowerCase()}
            </button>
          </article>
        ))}
      </div>
      <label className="radio">
        <input type="checkbox" checked={quick} onChange={(e) => setQuick(e.target.checked)} /> Quick run (60 s,
        fewer users): recommended on a laptop
      </label>

      {active && (
        <>
          <div className="row between">
            <h2>
              Running: run #{active.id} ({active.scenario})
            </h2>
            <button className="btn" disabled={busy} onClick={stop}>
              Stop
            </button>
          </div>
          {live ? (
            <>
              <div className="stats">
                <div className="card"><span className="muted">Users</span><strong>{live.users} / {active.target_users}</strong></div>
                <div className="card"><span className="muted">Requests/s</span><strong>{n(live.rps, 1)}</strong></div>
                <div className="card"><span className="muted">Requests</span><strong>{live.total_requests}</strong></div>
                <div className="card"><span className="muted">Failures</span><strong>{pct(live.failed_requests, live.total_requests)}</strong></div>
                <div className="card"><span className="muted">Avg / p95 ms</span><strong>{n(live.avg_response_ms)} / {n(live.p95_response_ms)}</strong></div>
                <div className="card"><span className="muted">Elapsed</span><strong>{live.elapsed_s}s / {active.duration_seconds}s</strong></div>
              </div>
              <table className="table">
                <thead><tr><th>Endpoint</th><th>Requests</th><th>Failures</th><th>Avg ms</th><th>p95 ms</th></tr></thead>
                <tbody>
                  {live.endpoints.map((e) => (
                    <tr key={e.name}><td>{e.name}</td><td>{e.requests}</td><td>{e.failures}</td><td>{e.avg_ms}</td><td>{n(e.p95_ms)}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="muted">Waiting for statistics from the load generator…</p>
          )}
        </>
      )}

      <h2>Run history</h2>
      {runs.length === 0 ? (
        <p className="muted">No runs yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr><th>#</th><th>Scenario</th><th>Status</th><th>Users</th><th>Started</th><th>Requests</th><th>Error rate</th><th>Avg ms</th><th>p95 ms</th><th>Peak RPS</th></tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.scenario}</td>
                <td><span className={`badge ${r.status === "COMPLETED" ? "status-completed" : r.status === "RUNNING" ? "status-preparing" : r.status === "FAILED" ? "status-failed" : "status-pending"}`}>{r.status}</span></td>
                <td>{r.target_users}</td>
                <td>{when(r.started_at)}</td>
                <td>{r.total_requests ?? "—"}</td>
                <td>{pct(r.failed_requests, r.total_requests)}</td>
                <td>{n(r.avg_response_ms)}</td>
                <td>{n(r.p95_response_ms)}</td>
                <td>{n(r.peak_rps, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
