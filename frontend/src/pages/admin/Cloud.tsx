import { useState } from "react";
import type { MouseEvent } from "react";
import { api, parseUtc, sectionError } from "../../api";
import type { CloudOverview, MetricPoint } from "../../api";
import { Alert, Empty, Loading } from "../../components/ui";
import { ago, time } from "../../format";
import { usePolling } from "../../hooks";

const usd = (v: number, digits = 2) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);

const hhmm = (ts: string) => parseUtc(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/**
 * One-series line chart for the last hour, with an optional dashed threshold line and a
 * crosshair tooltip. CPU and instance count are two separate charts on a shared time axis
 * (never one chart with two y-scales).
 */
function LineChart({
  points,
  yMax,
  unit,
  label,
  threshold,
  step,
  color,
  height = 170,
}: {
  points: MetricPoint[];
  yMax: number;
  unit: string;
  label: string;
  threshold?: { value: number; label: string } | null;
  step?: boolean;
  color: string;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640;
  const H = height;
  const pad = { l: 38, r: 12, t: 12, b: 24 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;

  if (points.length < 2) {
    return <p className="muted small chart-empty">Not enough data yet for {label.toLowerCase()} (CloudWatch reports every minute).</p>;
  }

  const t0 = parseUtc(points[0].t).getTime();
  const t1 = parseUtc(points[points.length - 1].t).getTime();
  const x = (t: string) => pad.l + ((parseUtc(t).getTime() - t0) / Math.max(1, t1 - t0)) * iw;
  const y = (v: number) => pad.t + ih - (Math.min(v, yMax) / yMax) * ih;

  let path = "";
  points.forEach((p, i) => {
    if (i === 0) path += `M${x(p.t)},${y(p.v)}`;
    else if (step) path += `H${x(p.t)}V${y(p.v)}`;
    else path += `L${x(p.t)},${y(p.v)}`;
  });
  const area = `${path}V${y(0)}H${x(points[0].t)}Z`;
  const ticks = [0, yMax / 2, yMax];
  const xTicks = [0, Math.floor(points.length / 2), points.length - 1];

  function onMove(e: MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    points.forEach((p, i) => {
      if (Math.abs(x(p.t) - px) < Math.abs(x(points[best].t) - px)) best = i;
    });
    setHover(best);
  }

  const hp = hover !== null ? points[hover] : null;
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}, last hour`} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="chart-grid" />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="chart-axis">{Number.isInteger(v) ? v : v.toFixed(1)}{unit}</text>
          </g>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={x(points[i].t)} y={H - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} className="chart-axis">
            {hhmm(points[i].t)}
          </text>
        ))}
        {threshold && (
          <g>
            <line x1={pad.l} x2={W - pad.r} y1={y(threshold.value)} y2={y(threshold.value)} className="chart-threshold" />
            <text x={W - pad.r} y={y(threshold.value) - 5} textAnchor="end" className="chart-axis">{threshold.label}</text>
          </g>
        )}
        <path d={area} fill={color} opacity={0.12} />
        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        {hp && (
          <g>
            <line x1={x(hp.t)} x2={x(hp.t)} y1={pad.t} y2={pad.t + ih} className="chart-cross" />
            <circle cx={x(hp.t)} cy={y(hp.v)} r={4.5} fill={color} stroke="var(--surface)" strokeWidth={2} />
          </g>
        )}
        <rect x={pad.l} y={pad.t} width={iw} height={ih} fill="transparent" />
      </svg>
      {hp && (
        <div className="chart-tip" style={{ left: `${(x(hp.t) / W) * 100}%` }}>
          <strong>{step ? hp.v : `${hp.v.toFixed(1)}${unit}`}</strong> <span className="muted">{label.toLowerCase()} · {hhmm(hp.t)}</span>
        </div>
      )}
    </div>
  );
}

function StateBadge({ state }: { state: string }) {
  const map: Record<string, [string, string]> = {
    ALARM: ["cloud-bad", "● Alarm"],
    OK: ["cloud-ok", "✓ OK"],
    INSUFFICIENT_DATA: ["cloud-idle", "… No data"],
    InService: ["cloud-ok", "✓ In service"],
    Healthy: ["cloud-ok", "✓ Healthy"],
    Unhealthy: ["cloud-bad", "● Unhealthy"],
    Successful: ["cloud-ok", "✓ Done"],
    Failed: ["cloud-bad", "● Failed"],
    Cancelled: ["cloud-idle", "Cancelled"],
  };
  const [cls, text] = map[state] ?? (state.startsWith("Pending") || state === "InProgress" ? ["cloud-warn", `◐ ${state}`] : ["cloud-idle", state]);
  return <span className={`badge ${cls}`}>{text}</span>;
}

export function Cloud() {
  const { data, error, loading } = usePolling(() => api<CloudOverview>("/api/admin/cloud"), 15000);

  if (loading && !data) return <Loading />;
  const head = (
    <header className="section-head">
      <div>
        <h1>Cloud &amp; cost</h1>
        <p className="muted">
          Live view of the AWS deployment: servers in the Auto Scaling Group, CPU against the scaling target, scaling
          history, alarms, and what it all costs per hour. Refreshes every 15 s.
        </p>
      </div>
      {data && (
        <p className="muted small cloud-meta">
          This page served by <code>{data.served_by}</code>
          {data.fetched_at && <> · AWS read at {time(data.fetched_at)}</>}
        </p>
      )}
    </header>
  );
  if (!data) return <>{head}<Alert>{error}</Alert></>;
  if (!data.configured) {
    return (
      <>
        {head}
        <Empty icon="☁️">
          <p><strong>Not running on AWS.</strong></p>
          <p className="muted">
            This panel reads the Auto Scaling Group, CloudWatch, RDS and AWS Budgets. It switches on when the app is deployed
            with <code>infra/scripts</code> (which sets <code>ASG_NAME</code> and friends).
          </p>
        </Empty>
      </>
    );
  }

  const asg = data.asg && !sectionError(data.asg) ? (data.asg as Exclude<CloudOverview["asg"], { error: string } | undefined>) : null;
  const metrics = data.metrics && !sectionError(data.metrics) ? (data.metrics as { cpu: MetricPoint[]; instances: MetricPoint[] }) : null;
  const activities = data.activities && !sectionError(data.activities) ? (data.activities as { items: { at: string | null; description: string; status: string; cause: string }[] }).items : null;
  const alarms = data.alarms && !sectionError(data.alarms) ? (data.alarms as { items: { name: string; state: string; reason: string; since: string | null; scaling: boolean }[] }).items : null;
  const budget = data.budget && !sectionError(data.budget) ? (data.budget as { limit: number | null; actual: number | null; forecast: number | null }) : null;
  const cost = data.cost!;

  const inService = asg?.instances.filter((i) => i.lifecycle === "InService").length ?? 0;
  const cpuNow = metrics?.cpu.length ? metrics.cpu[metrics.cpu.length - 1].v : null;
  const target = asg?.cpu_target ?? 60;
  const firing = alarms?.filter((a) => a.state === "ALARM" && !a.scaling).length ?? 0;
  const maxInstances = asg?.max ?? 4;
  const sectionErrors = [
    ["Auto Scaling Group", data.asg],
    ["CloudWatch metrics", data.metrics],
    ["Scaling activity", data.activities],
    ["Alarms", data.alarms],
    ["Budget", data.budget],
  ]
    .map(([name, s]) => (sectionError(s) ? `${name}: ${sectionError(s)}` : null))
    .filter(Boolean);

  return (
    <>
      {head}
      <Alert>{error}</Alert>
      {sectionErrors.length > 0 && (
        <Alert kind="info">
          Some AWS reads were refused, so parts of this page are missing: {sectionErrors.join(" · ")}
        </Alert>
      )}

      <section className="stats">
        <div className="card stat">
          <span className="stat-label">Servers in service</span>
          <span className="stat-value">{asg ? inService : "–"}<small> / {maxInstances} max</small></span>
          {asg && <span className="stat-sub muted">desired {asg.desired} · min {asg.min}</span>}
        </div>
        <div className="card stat">
          <span className="stat-label">Average CPU</span>
          <span className="stat-value">{cpuNow === null ? "–" : `${cpuNow.toFixed(0)}%`}</span>
          <span className="stat-sub muted">scales out above {target}%</span>
        </div>
        <div className="card stat">
          <span className="stat-label">Alarms firing</span>
          <span className="stat-value">{alarms ? firing : "–"}</span>
          <span className="stat-sub muted">{alarms ? `of ${alarms.filter((a) => !a.scaling).length} FeastFlow alarms` : "not available"}</span>
        </div>
        <div className="card stat">
          <span className="stat-label">Cost right now</span>
          <span className="stat-value">{usd(cost.per_hour, 3)}<small> / h</small></span>
          <span className="stat-sub muted">≈ {usd(cost.per_day)} per day if left on</span>
        </div>
      </section>

      <section className="two-col cloud-charts">
        <div className="card">
          <h2>Average CPU, last hour</h2>
          <p className="muted small">All servers in the group. Above the dashed line the target-tracking policy adds servers.</p>
          {metrics ? (
            <LineChart points={metrics.cpu} yMax={100} unit="%" label="Average CPU" color="var(--brand)" threshold={{ value: target, label: `target ${target}%` }} />
          ) : (
            <p className="muted small">CPU metrics unavailable.</p>
          )}
        </div>
        <div className="card">
          <h2>Servers in service, last hour</h2>
          <p className="muted small">Scale-out shows as steps up, scale-in as steps down.</p>
          {metrics ? (
            <LineChart points={metrics.instances} yMax={maxInstances} unit="" label="Servers in service" color="var(--info)" step />
          ) : (
            <p className="muted small">Instance metrics unavailable.</p>
          )}
        </div>
      </section>

      <section className="card table-wrap cloud-section">
        <h2>Servers {asg && <span className="muted small">· {asg.name}</span>}</h2>
        {asg ? (
          asg.instances.length ? (
            <table className="table">
              <thead>
                <tr><th>Instance</th><th>Zone</th><th>Type</th><th>State</th><th>Health</th><th>Running for</th></tr>
              </thead>
              <tbody>
                {asg.instances.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <code>{i.id}</code>
                      {i.id === data.served_by && <span className="badge cloud-here">this page</span>}
                    </td>
                    <td>{i.az}</td>
                    <td>{i.type}</td>
                    <td><StateBadge state={i.lifecycle ?? "?"} /></td>
                    <td><StateBadge state={i.health ?? "?"} /></td>
                    <td className="muted">{i.launched_at ? ago(i.launched_at).replace(" ago", "") : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No servers running: the group is scaled to 0 (parked for the night).</p>
          )
        ) : (
          <p className="muted">Auto Scaling Group not available.</p>
        )}
      </section>

      <section className="two-col">
        <div className="card table-wrap">
          <h2>Scaling activity</h2>
          {activities ? (
            activities.length ? (
              <ul className="cloud-activity">
                {activities.map((a, n) => (
                  <li key={n}>
                    <div className="row-between">
                      <strong>{a.description}</strong>
                      <StateBadge state={a.status} />
                    </div>
                    <span className="muted small">{a.at ? `${time(a.at)} · ${ago(a.at)}` : ""}</span>
                    {a.cause && <p className="muted small cloud-cause" title={a.cause}>{a.cause}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No scaling activity yet.</p>
            )
          ) : (
            <p className="muted">Scaling history unavailable.</p>
          )}
        </div>

        <div className="card table-wrap">
          <h2>Alarms</h2>
          {alarms ? (
            <table className="table compact">
              <thead><tr><th>State</th><th>Alarm</th><th>Since</th></tr></thead>
              <tbody>
                {alarms.map((a) => (
                  <tr key={a.name} className={a.scaling ? "dim" : undefined} title={a.reason}>
                    <td><StateBadge state={a.state} /></td>
                    <td>
                      {a.scaling ? "Auto scaling: " : ""}
                      {a.scaling ? (a.name.includes("AlarmHigh") ? "scale out (CPU high)" : "scale in (CPU low)") : a.name.replace(/^feastflow-/, "")}
                    </td>
                    <td className="muted">{a.since ? ago(a.since) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">Alarms unavailable.</p>
          )}
          <p className="muted small">Faded rows are the ASG's own scaling alarms: they act automatically and don't email anyone.</p>
        </div>
      </section>

      <section className="two-col">
        <div className="card table-wrap">
          <h2>Cost estimate</h2>
          <table className="table compact">
            <thead><tr><th>Resource</th><th>Qty</th><th>Per hour</th></tr></thead>
            <tbody>
              {cost.lines.map((l) => (
                <tr key={l.item} className={l.per_hour === 0 ? "dim" : undefined}>
                  <td>{l.item}<br /><span className="muted small">{l.note}</span></td>
                  <td>{Number.isInteger(l.qty) ? l.qty : l.qty.toFixed(0)}</td>
                  <td className="right">{usd(l.per_hour, 4)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr><th>Total now</th><th></th><th className="right">{usd(cost.per_hour, 4)}</th></tr>
            </tfoot>
          </table>
          {cost.unknown.length > 0 && <Alert kind="info">Couldn't read: {cost.unknown.join(", ")}. The total leaves them out.</Alert>}
          <p className="muted small">{cost.note}</p>
        </div>

        <div className="card">
          <h2>Budget</h2>
          <div className="cloud-proj">
            <div><span className="stat-label">8 h work day</span><strong>{usd(cost.per_hour * 8)}</strong></div>
            <div><span className="stat-label">24 h</span><strong>{usd(cost.per_day)}</strong></div>
            <div><span className="stat-label">Month, never stopped</span><strong>{usd(cost.per_month)}</strong></div>
          </div>
          {budget && budget.limit ? (
            <>
              <p className="cloud-budget-line">
                <strong>{usd(budget.actual ?? 0)}</strong> spent this month of the <strong>{usd(budget.limit, 0)}</strong> budget
                {budget.forecast !== null && <> · forecast {usd(budget.forecast)}</>}
              </p>
              <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={budget.limit} aria-valuenow={budget.actual ?? 0} aria-label="Budget used">
                <span style={{ width: `${Math.min(100, ((budget.actual ?? 0) / budget.limit) * 100)}%` }} />
              </div>
              <p className="muted small">From AWS Budgets, which refreshes a few times a day. Alerts email at 50 % and 80 %.</p>
            </>
          ) : (
            <p className="muted small">
              {sectionError(data.budget) ? "AWS Budgets couldn't be read from the server." : "No budget configured."} The Learner Lab page shows the credit used.
            </p>
          )}
          <p className="muted small">
            The nightly Lambda scales the group to 0 and stops RDS at 23:00 IST, so a parked night costs only the load balancer and storage.
          </p>
        </div>
      </section>
    </>
  );
}
