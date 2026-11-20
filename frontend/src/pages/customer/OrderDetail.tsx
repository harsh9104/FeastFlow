import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../../api";
import type { Order } from "../../api";
import { Alert, DeliveryRoute, Loading, OrderProgress, PrimeBadge, StatusBadge, Timeline } from "../../components/ui";
import { ACTIVE_STATUSES, money } from "../../format";
import { usePolling } from "../../hooks";

const MESSAGE: Partial<Record<Order["status"], [string, string]>> = {
  PLACED: ["🧾", "Order received! Sending it to the kitchen…"],
  CONFIRMED: ["👍", "The restaurant accepted your order."],
  PREPARING: ["👨‍🍳", "Your food is being freshly prepared."],
  AWAITING_PARTNER: ["🔎", "Food's ready. Finding the nearest rider…"],
  OUT_FOR_DELIVERY: ["🛵", "Your order is on the way!"],
  DELIVERED: ["😋", "Delivered. Enjoy your meal!"],
  CANCELLED: ["✖️", "This order was cancelled."],
};

export function OrderDetail() {
  const id = Number(useParams().id);
  const justPlaced = (useLocation().state as { justPlaced?: boolean } | null)?.justPlaced;
  const { data: order, error, loading } = usePolling(() => api<Order>(`/api/orders/${id}`), 3000, [id]);

  if (loading && !order) return <Loading label="Fetching your order…" />;
  if (!order) return <Alert>{error ?? "Order not found"}</Alert>;
  const live = ACTIVE_STATUSES.includes(order.status);
  const [icon, text] = MESSAGE[order.status] ?? ["", ""];

  return (
    <div className="order-detail">
      <nav className="crumbs">
        <Link to="/orders">My orders</Link> / <span>#{order.id}</span>
      </nav>

      <section className={`track-hero track-${order.status.toLowerCase()}`}>
        <div className="track-top">
          <div>
            <span className="track-kicker">{justPlaced && order.status === "PLACED" ? "🎉 Order placed" : `Order #${order.id}`}</span>
            <h1>
              <span className="track-icon">{icon}</span> {text}
            </h1>
            <p>{order.restaurant_name}{live && <span className="live-dot" title="Updating live" />}</p>
          </div>
          <div className="badges">
            {order.is_prime && <PrimeBadge />}
            <StatusBadge status={order.status} />
          </div>
        </div>
        <DeliveryRoute order={order} />
        <OrderProgress order={order} />
      </section>

      {order.partner_name && (
        <div className="card partner-card">
          <span className="avatar" aria-hidden>🧑‍🦱</span>
          <div>
            <strong>{order.partner_name}</strong>
            <p className="muted">{order.status === "DELIVERED" ? "delivered your order" : "is your delivery partner"}</p>
          </div>
          {order.partner_phone && order.status === "OUT_FOR_DELIVERY" && (
            <a className="btn small" href={`tel:${order.partner_phone}`}>📞 Call</a>
          )}
        </div>
      )}
      {error && <Alert kind="info">Live updates paused: {error}</Alert>}

      <div className="two-col">
        <section className="card">
          <h2>Order summary</h2>
          <ul className="summary-lines">
            {order.items.map((i) => (
              <li key={i.menu_item_id}>
                <span><span className="qty-chip">{i.quantity}×</span> {i.name}</span>
                <span>{money(Number(i.unit_price) * i.quantity)}</span>
              </li>
            ))}
          </ul>
          <div className="to-pay"><span>Paid (cash on delivery)</span><strong>{money(order.total_amount)}</strong></div>
          <p className="muted small-print">📍 {order.delivery_address}</p>
        </section>
        <section className="card">
          <h2>Timeline</h2>
          <Timeline order={order} />
        </section>
      </div>
    </div>
  );
}
