import { Link } from "react-router-dom";
import { api } from "../../api";
import type { Order, Page } from "../../api";
import { Alert, Empty, Loading, PrimeBadge, StatusBadge } from "../../components/ui";
import { ACTIVE_STATUSES, dateTime, money } from "../../format";
import { usePolling } from "../../hooks";

export function Orders() {
  const { data, error, loading } = usePolling(() => api<Page<Order>>("/api/orders?page_size=50"), 5000);

  if (loading) return <Loading label="Loading your orders…" />;
  if (error) return <Alert>{error}</Alert>;
  if (!data?.items.length) {
    return (
      <Empty icon="🧾">
        <h2>No orders yet</h2>
        <p className="muted">Your first feast is just a few taps away.</p>
        <Link to="/" className="btn primary">Find food</Link>
      </Empty>
    );
  }

  const active = data.items.filter((o) => ACTIVE_STATUSES.includes(o.status));
  const past = data.items.filter((o) => !ACTIVE_STATUSES.includes(o.status));
  return (
    <div className="orders-page">
      <h1 className="page-title">My orders</h1>
      {active.length > 0 && (
        <>
          <h2 className="section-title">Happening now <span className="live-dot" /></h2>
          <OrderList orders={active} live />
        </>
      )}
      {past.length > 0 && (
        <>
          <h2 className="section-title">Past orders</h2>
          <OrderList orders={past} />
        </>
      )}
    </div>
  );
}

function OrderList({ orders, live }: { orders: Order[]; live?: boolean }) {
  return (
    <ul className="order-list">
      {orders.map((o) => (
        <li key={o.id}>
          <Link to={`/orders/${o.id}`} className={`card order-row${live ? " live" : ""}`}>
            <span className="order-emoji" aria-hidden>{live ? "🛵" : "🍱"}</span>
            <div className="order-main">
              <strong>{o.restaurant_name}</strong>
              <p className="muted one-line">{o.items.map((i) => `${i.name} × ${i.quantity}`).join(", ")}</p>
              <small className="muted">#{o.id} · {dateTime(o.created_at)}</small>
            </div>
            <div className="order-row-side">
              <div className="badges">
                {o.is_prime && <PrimeBadge small />}
                <StatusBadge status={o.status} />
              </div>
              <strong>{money(o.total_amount)}</strong>
              <span className="link-text">{live ? "Track order →" : "View details →"}</span>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
