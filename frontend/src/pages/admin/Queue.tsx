import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Order, Stats } from "../../api/types";
import { PriorityBadge, StatusBadge, money, when } from "../../components/Badges";

const base = "/admin/orders";
const fmt = (s: number | null) => (s === null ? "—" : s < 120 ? `${Math.round(s)} s` : `${(s / 60).toFixed(1)} min`);

export default function Queue() {
  const [queue, setQueue] = useState<Order[]>([]);
  const [preparing, setPreparing] = useState<Order[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [q, p, s] = await Promise.all([
        api<{ items: Order[] }>(`${base}/queue?limit=100`),
        api<{ items: Order[] }>(`${base}?status=PREPARING&page_size=50`),
        api<Stats>(`${base}/stats`),
      ]);
      setQueue(q.items);
      setPreparing(p.items);
      setStats(s);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      load();
    }
  }

  const claim = () => act(() => api(`${base}/queue/next`, { method: "POST" }));
  const complete = (o: Order) =>
    act(() => api(`${base}/${o.id}/status`, { method: "PATCH", body: { status: "COMPLETED", version: o.version } }));

  return (
    <section>
      <div className="row between">
        <h1>Order queue</h1>
        <button className="btn primary" disabled={busy || queue.length === 0} onClick={claim}>
          Claim next order
        </button>
      </div>
      {error && <p className="error">{error}</p>}

      {stats && (
        <div className="stats">
          <div className="card"><span className="muted">Pending</span><strong>{stats.counts_by_status.PENDING}</strong></div>
          <div className="card"><span className="muted">Preparing</span><strong>{stats.counts_by_status.PREPARING}</strong></div>
          <div className="card"><span className="muted">Completed</span><strong>{stats.counts_by_status.COMPLETED}</strong></div>
          <div className="card"><span className="muted">Avg wait ★ Premium</span><strong>{fmt(stats.avg_wait_premium_s)}</strong></div>
          <div className="card"><span className="muted">Avg wait Free</span><strong>{fmt(stats.avg_wait_free_s)}</strong></div>
        </div>
      )}

      <h2>Pending (Premium first, then oldest)</h2>
      <OrderTable orders={queue} empty="Queue is empty." showPosition />

      <h2>Preparing</h2>
      <OrderTable
        orders={preparing}
        empty="Nothing in preparation."
        action={(o) => (
          <button className="btn small primary" disabled={busy} onClick={() => complete(o)}>
            Mark completed
          </button>
        )}
      />
    </section>
  );
}

export function OrderTable({
  orders,
  empty,
  action,
  showPosition,
}: {
  orders: Order[];
  empty: string;
  action?: (o: Order) => React.ReactNode;
  showPosition?: boolean;
}) {
  if (orders.length === 0) return <p className="muted">{empty}</p>;
  return (
    <table className="table">
      <thead>
        <tr>
          {showPosition && <th>#</th>}
          <th>Order</th>
          <th>Customer</th>
          <th>Items</th>
          <th>Priority</th>
          <th>Status</th>
          <th>Total</th>
          <th>Placed</th>
          {action && <th />}
        </tr>
      </thead>
      <tbody>
        {orders.map((o, n) => (
          <tr key={o.id}>
            {showPosition && <td>{n + 1}</td>}
            <td>#{o.id}</td>
            <td>{o.customer}</td>
            <td>{o.items.map((i) => `${i.quantity}× ${i.name}`).join(", ")}</td>
            <td><PriorityBadge tier={o.tier_at_order} /></td>
            <td><StatusBadge status={o.status} /></td>
            <td>{money(o.total_amount)}</td>
            <td>{when(o.created_at)}</td>
            {action && <td>{action(o)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
