import { useEffect, useState } from "react";
import { api } from "../../api";
import type { DispatchStats, Order, OrderStatus, Page } from "../../api";
import { Alert, Loading, PrimeBadge, StatusBadge } from "../../components/ui";
import { ago, money, seconds } from "../../format";
import { usePolling } from "../../hooks";

const COLUMNS: { title: string; statuses: OrderStatus[]; hint: string }[] = [
  { title: "New", statuses: ["PLACED", "CONFIRMED"], hint: "Taken from SQS, Prime first" },
  { title: "Preparing", statuses: ["PREPARING"], hint: "In the kitchen" },
  { title: "Waiting for rider", statuses: ["AWAITING_PARTNER"], hint: "Food ready, no partner free" },
  { title: "On the way", statuses: ["OUT_FOR_DELIVERY"], hint: "Partner assigned" },
];
const CARDS_PER_COLUMN = 40; // festival days can have hundreds; the rest are counted

export function Board() {
  const { data, error, loading } = usePolling(async () => {
    const [stats, active, delivered] = await Promise.all([
      api<DispatchStats>("/api/admin/dispatch/stats"),
      api<Page<Order>>("/api/admin/orders?status=ACTIVE&page_size=200"),
      api<Page<Order>>("/api/admin/orders?status=DELIVERED&page_size=8"),
    ]);
    return { stats, active, delivered };
  }, 3000);

  // Re-render every second so "x s ago" stays current between polls.
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  if (loading && !data) return <Loading />;
  if (!data) return <Alert>{error}</Alert>;
  const { stats, active, delivered } = data;

  return (
    <>
      <header className="section-head">
        <div>
          <h1>Dispatch board</h1>
          <p className="muted">
            Live view of every open order. Refreshes every 3 s<span className="live-dot" />
          </p>
        </div>
      </header>
      {error && <Alert kind="info">Last refresh failed: {error}</Alert>}

      <section className="stats">
        <Stat label="SQS: Prime queue" value={stats.queues.prime?.waiting ?? "?"}
          sub={stats.queues.prime ? `${stats.queues.prime.in_flight} being processed` : "unavailable"} accent="prime" />
        <Stat label="SQS: Standard queue" value={stats.queues.standard?.waiting ?? "?"}
          sub={stats.queues.standard ? `${stats.queues.standard.in_flight} being processed` : "unavailable"} />
        <Stat label="Open orders" value={active.total}
          sub={`${stats.orders_by_status.AWAITING_PARTNER} waiting for a rider`} />
        <Stat label="Partners free" value={`${stats.partners.AVAILABLE} / ${stats.partners.AVAILABLE + stats.partners.BUSY}`}
          sub={`${stats.partners.BUSY} on delivery · ${stats.partners.OFFLINE} offline`} />
        <Stat label="Delivered" value={stats.orders_by_status.DELIVERED} sub="all time" />
      </section>

      <section className="card waits">
        <h2>Prime vs standard, last {stats.window_minutes} min</h2>
        <table className="table compact">
          <thead>
            <tr>
              <th></th>
              <th>Orders</th>
              <th>Time to confirm</th>
              <th>Wait for rider</th>
              <th>Order to door</th>
            </tr>
          </thead>
          <tbody>
            {(["prime", "standard"] as const).map((k) => (
              <tr key={k}>
                <th>{k === "prime" ? <PrimeBadge small /> : "Standard"}</th>
                <td>{stats[k].orders}</td>
                <td>{seconds(stats[k].avg_seconds_to_confirm)}</td>
                <td>{seconds(stats[k].avg_seconds_waiting_for_partner)}</td>
                <td>{seconds(stats[k].avg_seconds_to_deliver)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {active.total > active.items.length && (
        <Alert kind="info">
          Showing the {active.items.length} most urgent of {active.total} open orders.
        </Alert>
      )}
      <section className="board">
        {COLUMNS.map((col) => {
          const orders = active.items.filter((o) => col.statuses.includes(o.status));
          return (
            <div key={col.title} className="column">
              <header>
                <h3>{col.title}</h3>
                <span className="pill">{orders.length}</span>
              </header>
              <p className="muted hint">{col.hint}</p>
              {orders.slice(0, CARDS_PER_COLUMN).map((o) => (
                <OrderCard key={o.id} order={o} now={now} />
              ))}
              {orders.length > CARDS_PER_COLUMN && (
                <p className="muted more">+{orders.length - CARDS_PER_COLUMN} more</p>
              )}
              {orders.length === 0 && <p className="muted none">Nothing here</p>}
            </div>
          );
        })}
      </section>

      <section className="card">
        <h2>Recently delivered</h2>
        {delivered.items.length === 0 ? (
          <p className="muted">No deliveries yet.</p>
        ) : (
          <table className="table compact">
            <tbody>
              {delivered.items.map((o) => (
                <tr key={o.id}>
                  <td>#{o.id}</td>
                  <td>{o.is_prime && <PrimeBadge small />}</td>
                  <td>{o.customer_name}</td>
                  <td className="muted">{o.restaurant_name}</td>
                  <td>{o.partner_name}</td>
                  <td>{money(o.total_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function Stat({ label, value, sub, accent }: { label: string; value: string | number; sub: string; accent?: "prime" }) {
  return (
    <div className={`card stat${accent ? ` ${accent}` : ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      <span className="muted stat-sub">{sub}</span>
    </div>
  );
}

function OrderCard({ order, now }: { order: Order; now: number }) {
  const items = order.items.reduce((n, i) => n + i.quantity, 0);
  return (
    <article className={`order-card${order.is_prime ? " is-prime" : ""}`}>
      <div className="order-card-top">
        <strong>#{order.id}</strong>
        {order.is_prime && <PrimeBadge small />}
        <span className="muted age">{ago(order.created_at, now)}</span>
      </div>
      <div>{order.customer_name} · <span className="muted">{order.restaurant_name}</span></div>
      <div className="muted">{items} item{items > 1 ? "s" : ""} · {money(order.total_amount)}</div>
      <div className="order-card-bottom">
        <StatusBadge status={order.status} />
        {order.partner_name && <span>🛵 {order.partner_name}</span>}
      </div>
    </article>
  );
}
