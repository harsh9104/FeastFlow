import type { ReactNode } from "react";
import type { Order, OrderStatus } from "../api";
import { STATUS_LABEL, STEPS, time } from "../format";

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

export function Alert({ kind = "error", children }: { kind?: "error" | "info" | "success"; children: ReactNode }) {
  if (!children) return null;
  return (
    <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="muted loading">{label}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** Step tracker for customers: Placed → Confirmed → Preparing → On the way → Delivered. */
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
