import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../../api";
import type { Order } from "../../api";
import { Alert, Loading, OrderProgress, PrimeBadge, StatusBadge, Timeline } from "../../components/ui";
import { ACTIVE_STATUSES, money } from "../../format";
import { usePolling } from "../../hooks";

const MESSAGE: Partial<Record<Order["status"], string>> = {
  PLACED: "Order received. Sending it to the restaurant…",
  CONFIRMED: "The restaurant has accepted your order.",
  PREPARING: "Your food is being prepared.",
  AWAITING_PARTNER: "Your food is ready. Finding a delivery partner…",
  OUT_FOR_DELIVERY: "Your order is on the way!",
  DELIVERED: "Delivered. Enjoy your meal!",
};

export function OrderDetail() {
  const id = Number(useParams().id);
  const justPlaced = (useLocation().state as { justPlaced?: boolean } | null)?.justPlaced;
  const { data: order, error, loading } = usePolling(() => api<Order>(`/api/orders/${id}`), 3000, [id]);

  if (loading && !order) return <Loading />;
  if (!order) return <Alert>{error ?? "Order not found"}</Alert>;
  const live = ACTIVE_STATUSES.includes(order.status);

  return (
    <div className="order-detail">
      <Link to="/orders" className="back">← My orders</Link>
      {justPlaced && order.status === "PLACED" && <Alert kind="success">Order placed!</Alert>}
      <section className="card">
        <header className="section-head">
          <div>
            <h1>Order #{order.id}</h1>
            <p className="muted">{order.restaurant_name}</p>
          </div>
          <div className="badges">
            {order.is_prime && <PrimeBadge />}
            <StatusBadge status={order.status} />
          </div>
        </header>
        <OrderProgress order={order} />
        <p className="status-message">
          {MESSAGE[order.status]}
          {live && <span className="live-dot" title="Updating live" />}
        </p>
        {order.partner_name && (
          <div className="partner-card">
            <span className="avatar" aria-hidden>🛵</span>
            <div>
              <strong>{order.partner_name}</strong>
              <p className="muted">{order.status === "DELIVERED" ? "Delivered your order" : "Your delivery partner"}</p>
            </div>
            {order.partner_phone && order.status === "OUT_FOR_DELIVERY" && (
              <a className="btn small" href={`tel:${order.partner_phone}`}>Call</a>
            )}
          </div>
        )}
        {error && <Alert kind="info">Live updates paused: {error}</Alert>}
      </section>

      <div className="two-col">
        <section className="card">
          <h2>Items</h2>
          <ul className="cart-lines readonly">
            {order.items.map((i) => (
              <li key={i.menu_item_id}>
                <span className="name">{i.quantity}× {i.name}</span>
                <span className="amount">{money(Number(i.unit_price) * i.quantity)}</span>
              </li>
            ))}
          </ul>
          <div className="total-row">
            <span>Total</span>
            <strong>{money(order.total_amount)}</strong>
          </div>
          <p className="muted small-print">Deliver to: {order.delivery_address}</p>
        </section>
        <section className="card">
          <h2>Timeline</h2>
          <Timeline order={order} />
        </section>
      </div>
    </div>
  );
}
