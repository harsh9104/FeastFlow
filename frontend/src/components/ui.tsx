import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { MenuItem, Order, OrderStatus, Restaurant } from "../api";
import { CUISINE_EMOJI } from "../catalog";
import { STATUS_LABEL, STEPS, time } from "../format";
import { IconClock, IconStar } from "./icons";

export function StatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>;
}

export function PrimeBadge({ small }: { small?: boolean }) {
  return <span className={`badge prime${small ? " small" : ""}`}>★ Prime</span>;
}

export function VegMark({ veg }: { veg: boolean }) {
  return (
    <span className={`veg-mark ${veg ? "veg" : "nonveg"}`} title={veg ? "Vegetarian" : "Non-vegetarian"}>
      <span />
    </span>
  );
}

export function Rating({ value }: { value: string | number }) {
  const n = Number(value);
  return (
    <span className={`rating ${n >= 4.3 ? "great" : n >= 3.8 ? "good" : "ok"}`}>
      <IconStar /> {n.toFixed(1)}
    </span>
  );
}

export function Alert({ kind = "error", children }: { kind?: "error" | "info" | "success"; children: ReactNode }) {
  if (!children) return null;
  return (
    <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function Empty({ icon = "🍽️", children }: { icon?: string; children: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-icon" aria-hidden>{icon}</span>
      {children}
    </div>
  );
}

/** Dish photo with a graceful fallback when there's no image or it fails to load. */
export function DishImage({ item, className = "" }: { item: Pick<MenuItem, "name" | "image_url">; className?: string }) {
  return (
    <div className={`dish-photo ${className}`}>
      {item.image_url ? (
        <img
          src={item.image_url}
          alt={item.name}
          loading="lazy"
          onError={(e) => ((e.currentTarget.style.visibility = "hidden"))}
        />
      ) : (
        <span aria-hidden>🍽️</span>
      )}
    </div>
  );
}

export function RestaurantCard({ restaurant: r, cover }: { restaurant: Restaurant; cover: string | null }) {
  return (
    <Link to={`/restaurants/${r.id}`} className={`rest-card${r.is_open ? "" : " closed"}`}>
      <div className="rest-cover">
        {cover ? <img src={cover} alt="" loading="lazy" /> : <span className="rest-cover-emoji">{CUISINE_EMOJI[r.cuisine] ?? "🍽️"}</span>}
        <div className="rest-cover-shade" />
        {r.offer && <span className="rest-offer">{r.offer}</span>}
        {!r.is_open && <span className="rest-closed">Closed now</span>}
      </div>
      <div className="rest-body">
        <h3>{r.name}</h3>
        <div className="rest-meta">
          <Rating value={r.rating} />
          <span className="dot-sep">•</span>
          <span className="eta"><IconClock /> {r.delivery_minutes}–{r.delivery_minutes + 5} mins</span>
        </div>
        <p className="muted one-line">{r.cuisine}</p>
        <p className="muted one-line small">{r.area} · ₹{r.cost_for_two} for two</p>
      </div>
    </Link>
  );
}

/** Restaurant → rider → home route with the rider moving as the order progresses. */
export function DeliveryRoute({ order }: { order: Order }) {
  const pos: Record<OrderStatus, number> = {
    PLACED: 4, CONFIRMED: 10, PREPARING: 18, AWAITING_PARTNER: 24,
    OUT_FOR_DELIVERY: 62, DELIVERED: 96, CANCELLED: 4,
  };
  const p = pos[order.status];
  return (
    <div className="route" aria-hidden>
      <span className="route-end start">🏪</span>
      <div className="route-track">
        <div className="route-fill" style={{ width: `${p}%` }} />
        <span className={`route-rider${order.status === "OUT_FOR_DELIVERY" ? " moving" : ""}`} style={{ left: `${p}%` }}>
          {order.status === "DELIVERED" ? "✅" : order.partner_name ? "🛵" : "🍳"}
        </span>
      </div>
      <span className="route-end finish">🏠</span>
    </div>
  );
}

export function OrderProgress({ order }: { order: Order }) {
  const current = order.status === "AWAITING_PARTNER" ? "PREPARING" : order.status;
  const idx = STEPS.indexOf(current);
  return (
    <ol className="progress" aria-label="Order progress">
      {STEPS.map((s, i) => (
        <li key={s} className={i < idx ? "done" : i === idx ? "current" : ""}>
          <span className="dot" />
          <span className="label">{STATUS_LABEL[s]}</span>
        </li>
      ))}
    </ol>
  );
}

export function Timeline({ order }: { order: Order }) {
  return (
    <ul className="timeline">
      {order.events.map((e, i) => (
        <li key={i}>
          <span className="t">{time(e.created_at)}</span>
          <StatusBadge status={e.status} />
          {e.note && <span className="muted"> {e.note}</span>}
        </li>
      ))}
    </ul>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>
        {children}
      </div>
    </div>
  );
}
