import { Link } from "react-router-dom";
import { api } from "../../api";
import type { Order, Page } from "../../api";
import { Alert, Empty, Loading, PrimeBadge, StatusBadge } from "../../components/ui";
import { ACTIVE_STATUSES, dateTime, money } from "../../format";
import { usePolling } from "../../hooks";

export function Orders() {
  const { data, error, loading } = usePolling(() => api<Page<Order>>("/api/orders?page_size=50"), 5000);

  if (loading) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data?.items.length) {
    return (
      <Empty>
        <p>No orders yet.</p>
        <Link to="/" className="btn primary">Order something</Link>
      </Empty>
    );
  }

  const active = data.items.filter((o) => ACTIVE_STATUSES.includes(o.status));
  const past = data.items.filter((o) => !ACTIVE_STATUSES.includes(o.status));
  return (
    <>
      <h1>My orders</h1>
      {active.length > 0 && (
        <>
          <h2>In progress</h2>
          <OrderList orders={active} />
        </>
      )}
      {past.length > 0 && (
        <>
          <h2>Past orders</h2>
          <OrderList orders={past} />
        </>
      )}
    </>
  );
}

function OrderList({ orders }: { orders: Order[] }) {
  return (
    <ul className="order-list">
      {orders.map((o) => (
        <li key={o.id}>
          <Link to={`/orders/${o.id}`} className="card order-row">
            <div>
              <strong>#{o.id} · {o.restaurant_name}</strong>
              <p className="muted">
                {o.items.map((i) => `${i.quantity}× ${i.name}`).join(", ")}
              </p>
              <small className="muted">{dateTime(o.created_at)}</small>
            </div>
            <div className="order-row-side">
              <StatusBadge status={o.status} />
              {o.is_prime && <PrimeBadge small />}
              <strong>{money(o.total_amount)}</strong>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
