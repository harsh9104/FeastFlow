import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { when } from "../../components/Badges";
import MetricChart, { COLORS } from "../../components/MetricChart";
import type { Series } from "../../components/MetricChart";

interface Metrics {
  provider: "local" | "cloudwatch";
  range: string;
  period_s: number;
  series: Record<string, Series>;
  unavailable: string[];
}
interface Instance {
  instance_id: string;
  az: string;
  lifecycle_state: string;
  health_status: string;
  target_health: string;
  launch_time: string | null;
  type: string;
}
interface Alarm {
  name: string;
  state: "OK" | "ALARM" | "INSUFFICIENT_DATA";
  reason: string;
  updated_at: string;
}
interface Activity {
  start_time: string;
  status: string;
  description: string;
  cause: string;
}

const RANGES = ["15m", "1h", "3h", "24h"];
const last = (s?: Series) => [...(s?.points ?? [])].reverse().find((p) => p.v !== null)?.v ?? null;
const fmt = (v: number | null, d = 0, suffix = "") => (v === null ? "—" : `${v.toFixed(d)}${suffix}`);

export default function Dashboard() {
  const [range, setRange] = useState("1h");
  const [m, setM] = useState<Metrics | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [metrics, inst, al, act] = await Promise.all([
        api<Metrics>(`/admin/cloud/metrics?range=${range}`),
        api<Instance[]>("/admin/cloud/instances"),
        api<Alarm[]>("/admin/cloud/alarms"),
        api<Activity[]>("/admin/cloud/scaling-activities"),
      ]);
      setM(metrics);
      setInstances(inst);
      setAlarms(al);
      setActivities(act);
      setUpdated(new Date());
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [range]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const s = m?.series ?? {};
  const firing = alarms.filter((a) => a.state === "ALARM").length;
  const requests = (s.request_count?.points ?? []).reduce((n, p) => n + (p.v ?? 0), 0);
  const errors = (s.http_5xx?.points ?? []).reduce((n, p) => n + (p.v ?? 0), 0);

  return (
    <section>
      <div className="row between">
        <h1>Dashboard</h1>
        <div className="row">
          {m && <span className="badge tier-free">{m.provider === "local" ? "Local metrics" : "CloudWatch"}</span>}
          <select value={range} onChange={(e) => setRange(e.target.value)} aria-label="Time range">
            {RANGES.map((r) => (
              <option key={r} value={r}>
                Last {r}
              </option>
            ))}
          </select>
          <button className="btn small" onClick={load}>
            Refresh
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {updated && <p className="muted">Updated {updated.toLocaleTimeString()} · refreshes every 30 s</p>}

      <div className="stats">
        <div className="card"><span className="muted">Instances in service</span><strong>{fmt(last(s.in_service_instances))}</strong></div>
        <div className="card"><span className="muted">CPU (avg)</span><strong>{fmt(last(s.cpu_avg), 1, " %")}</strong></div>
        <div className="card"><span className="muted">Memory</span><strong>{fmt(last(s.mem_used_pct), 1, " %")}</strong></div>
        <div className="card"><span className="muted">Requests ({range})</span><strong>{requests}</strong></div>
        <div className="card"><span className="muted">5xx errors</span><strong>{errors}</strong></div>
        <div className="card"><span className="muted">Alarms firing</span><strong className={firing ? "error" : ""}>{firing}</strong></div>
      </div>

      <div className="charts">
        <MetricChart
          title="CPU & memory (%)"
          series={s}
          unit="%"
          domain={[0, 100]}
          lines={[
            { key: "cpu_avg", label: "CPU", color: COLORS.blue },
            { key: "mem_used_pct", label: "Memory", color: COLORS.violet },
          ]}
        />
        <MetricChart
          title="Traffic (requests per period)"
          series={s}
          lines={[
            { key: "request_count", label: "Requests", color: COLORS.green },
            { key: "http_5xx", label: "5xx", color: COLORS.red },
          ]}
        />
        <MetricChart
          title="Response time (ms)"
          series={s}
          lines={[
            { key: "target_response_time_p50", label: "p50", color: COLORS.blue, scale: 1000 },
            { key: "target_response_time_p90", label: "p90", color: COLORS.orange, scale: 1000 },
          ]}
        />
        <MetricChart
          title="Fleet size & health"
          series={s}
          lines={[
            { key: "in_service_instances", label: "In service", color: COLORS.green, step: true },
            { key: "healthy_hosts", label: "Healthy", color: COLORS.blue, step: true },
            { key: "unhealthy_hosts", label: "Unhealthy", color: COLORS.red, step: true },
          ]}
        />
        {m?.provider === "cloudwatch" && (
          <MetricChart
            title="Database"
            series={s}
            lines={[
              { key: "rds_cpu", label: "RDS CPU %", color: COLORS.orange },
              { key: "rds_connections", label: "Connections", color: COLORS.violet },
            ]}
          />
        )}
      </div>
      {m && m.unavailable.length > 0 && (
        <p className="muted">Not available with this provider: {m.unavailable.join(", ")}.</p>
      )}

      <h2>Alarms</h2>
      <table className="table">
        <thead><tr><th>Alarm</th><th>State</th><th>Reason</th></tr></thead>
        <tbody>
          {alarms.map((a) => (
            <tr key={a.name}>
              <td>{a.name}</td>
              <td>
                <span className={`badge ${a.state === "ALARM" ? "status-failed" : a.state === "OK" ? "status-completed" : "tier-free"}`}>
                  {a.state}
                </span>
              </td>
              <td className="muted">{a.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Instances</h2>
      {instances.length === 0 ? (
        <p className="muted">No instance has reported yet.</p>
      ) : (
        <table className="table">
          <thead><tr><th>Instance</th><th>AZ</th><th>State</th><th>Health</th><th>Target</th><th>Type</th><th>Since</th></tr></thead>
          <tbody>
            {instances.map((i) => (
              <tr key={i.instance_id}>
                <td>{i.instance_id}</td>
                <td>{i.az}</td>
                <td>{i.lifecycle_state}</td>
                <td>{i.health_status}</td>
                <td>{i.target_health}</td>
                <td>{i.type}</td>
                <td>{i.launch_time ? when(i.launch_time) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Scaling activity</h2>
      {activities.length === 0 ? (
        <p className="muted">
          {m?.provider === "local"
            ? "No auto scaling locally (single container). On AWS this lists the last 20 ASG scale-out and scale-in events."
            : "No scaling activity yet."}
        </p>
      ) : (
        <table className="table">
          <thead><tr><th>Time</th><th>Status</th><th>Description</th><th>Cause</th></tr></thead>
          <tbody>
            {activities.map((a) => (
              <tr key={a.start_time + a.description}>
                <td>{when(a.start_time)}</td>
                <td>{a.status}</td>
                <td>{a.description}</td>
                <td className="muted">{a.cause}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
