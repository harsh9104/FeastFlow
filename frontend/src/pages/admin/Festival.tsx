import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../../api";
import type { FestivalRun, LoadTestStatus } from "../../api";
import { Alert, Loading } from "../../components/ui";
import { dateTime } from "../../format";
import { usePolling } from "../../hooks";

const PRESETS = [
  { label: "Lunch rush", orders: 100, duration: 60, prime: 30 },
  { label: "Festival evening", orders: 500, duration: 120, prime: 30 },
  { label: "Prime flood", orders: 300, duration: 60, prime: 80 },
];

export function Festival() {
  return (
    <>
      <header className="section-head">
        <div>
          <h1>Festival day</h1>
          <p className="muted">
            Flood the system with orders and watch the queues, riders and Prime priority on the{" "}
            <Link to="/admin">dispatch board</Link>.
          </p>
        </div>
      </header>
      <OrderBurst />
      <LoadGenerator />
    </>
  );
}

// ---- in-app order burst ---------------------------------------------------------

function OrderBurst() {
  const { data: runs, error, refresh } = usePolling(() => api<FestivalRun[]>("/api/admin/festival/runs"), 2000);
  const [orders, setOrders] = useState(500);
  const [duration, setDuration] = useState(120);
  const [prime, setPrime] = useState(30);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const running = runs?.find((r) => r.status === "RUNNING");

  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await api("/api/admin/festival/runs", {
        method: "POST",
        body: { orders, duration_seconds: duration, prime_percent: prime },
      });
      await refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't start the run");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(id: number) {
    try {
      await api(`/api/admin/festival/runs/${id}/cancel`, { method: "POST" });
      await refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't cancel");
    }
  }

  return (
    <section className="card festival">
      <h2>Order burst</h2>
      <p className="muted">
        Places real orders from the seeded festival customers through the normal checkout: database, then SQS, then the
        worker. Shows Prime priority and rider shortage clearly. It doesn't create much HTTP load, so use the load
        generator below to make the Auto Scaling Group react.
      </p>

      {running ? (
        <RunProgress run={running} onCancel={() => cancel(running.id)} />
      ) : (
        <form className="form" onSubmit={start}>
          <div className="presets">
            {PRESETS.map((p) => (
              <button
                type="button"
                key={p.label}
                className="btn small ghost"
                onClick={() => {
                  setOrders(p.orders);
                  setDuration(p.duration);
                  setPrime(p.prime);
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="form-grid">
            <label>
              Orders
              <input type="number" min={1} max={5000} value={orders} onChange={(e) => setOrders(Number(e.target.value))} required />
            </label>
            <label>
              Over (seconds)
              <input type="number" min={0} max={1800} value={duration} onChange={(e) => setDuration(Number(e.target.value))} required />
              <small className="muted">0 = as fast as possible</small>
            </label>
            <label>
              Prime share: {prime}%
              <input type="range" min={0} max={100} step={5} value={prime} onChange={(e) => setPrime(Number(e.target.value))} />
            </label>
          </div>
          <p className="muted">
            About {duration ? (orders / duration).toFixed(1) : "max"} orders per second, {Math.round((orders * prime) / 100)} of them Prime.
          </p>
          <Alert>{formError}</Alert>
          <button className="btn primary" disabled={busy}>
            {busy ? "Starting…" : "🎉 Start festival burst"}
          </button>
        </form>
      )}

      <Alert>{error}</Alert>
      {runs && runs.length > 0 && (
        <div className="table-wrap">
          <h3>Recent runs</h3>
          <table className="table compact">
            <thead>
              <tr><th>#</th><th>Started</th><th>Status</th><th>Orders</th><th>Prime</th><th>Over</th><th>Instance</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td className="muted">{dateTime(r.started_at)}</td>
                  <td>
                    <span className={`badge run-${r.status.toLowerCase()}`}>{r.status.toLowerCase()}</span>
                    {r.error && <small className="muted"> {r.error}</small>}
                  </td>
                  <td>{r.created_orders} / {r.requested_orders}{r.failed_orders > 0 && <small className="muted"> ({r.failed_orders} rejected)</small>}</td>
                  <td>{r.prime_orders} ({r.prime_percent}%)</td>
                  <td>{r.duration_seconds}s</td>
                  <td className="muted">{r.instance_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RunProgress({ run, onCancel }: { run: FestivalRun; onCancel: () => void }) {
  const pct = Math.round((run.created_orders / run.requested_orders) * 100);
  return (
    <div className="run-progress">
      <div className="row-between">
        <strong>
          Run #{run.id}: {run.created_orders} of {run.requested_orders} orders
          <span className="live-dot" />
        </strong>
        <button className="btn small ghost" onClick={onCancel}>Stop</button>
      </div>
      <div className="bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <p className="muted">
        {run.prime_orders} Prime so far · running on {run.instance_id} · progress saves every 20 orders
      </p>
    </div>
  );
}

// ---- Locust load generator --------------------------------------------------------

function LoadGenerator() {
  const { data, error, refresh } = usePolling(() => api<LoadTestStatus>("/api/admin/loadtest"), 3000);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const active = data && ["spawning", "running"].includes(data.state);

  async function act(path: "start" | "stop", profile?: "normal" | "festival") {
    setBusy(true);
    setActionError(null);
    try {
      await api(`/api/admin/loadtest/${path}`, { method: "POST", body: profile ? { profile } : undefined });
      await refresh();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card festival">
      <h2>Load generator (Locust)</h2>
      <p className="muted">
        Simulated customers send real HTTP traffic through the load balancer: logging in, browsing, ordering and tracking
        orders. The <strong>festival</strong> profile runs for 20 minutes and peaks at 450 users, enough to push CPU past
        the scaling target so new EC2 instances join and later leave. <strong>Normal</strong> is 20 users for 10 minutes.
      </p>

      {error ? (
        <Alert kind="info">{error}</Alert>
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <div className="stats">
            <div className="card stat"><span className="stat-label">State</span><span className="stat-value small">{data.state}</span></div>
            <div className="card stat"><span className="stat-label">Users</span><span className="stat-value">{data.users}</span></div>
            <div className="card stat"><span className="stat-label">Requests / s</span><span className="stat-value">{data.rps}</span></div>
            <div className="card stat"><span className="stat-label">p95 latency</span><span className="stat-value">{data.p95_ms ?? "–"}<small> ms</small></span></div>
            <div className="card stat">
              <span className="stat-label">Failures</span>
              <span className="stat-value">{(data.fail_ratio * 100).toFixed(2)}%</span>
              <span className="muted stat-sub">{data.failures} of {data.requests}</span>
            </div>
          </div>
          {data.errors.length > 0 && (
            <Alert kind="info">
              {data.errors.map((e) => `${e.count}× ${e.name}: ${e.error}`).join(" · ")}
            </Alert>
          )}
          <div className="row-start">
            {active ? (
              <button className="btn" disabled={busy} onClick={() => act("stop")}>Stop load test</button>
            ) : (
              <>
                <button className="btn primary" disabled={busy} onClick={() => act("start", "festival")}>Start festival profile</button>
                <button className="btn" disabled={busy} onClick={() => act("start", "normal")}>Start normal profile</button>
              </>
            )}
          </div>
        </>
      )}
      <Alert>{actionError}</Alert>
    </section>
  );
}
