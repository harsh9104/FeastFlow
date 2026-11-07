import type { OrderStatus, Tier } from "../api/types";

export const StatusBadge = ({ status }: { status: OrderStatus }) => (
  <span className={`badge status-${status.toLowerCase()}`}>{status}</span>
);

export const PriorityBadge = ({ tier }: { tier: Tier }) => (
  <span className={`badge tier-${tier.toLowerCase()}`}>{tier === "PREMIUM" ? "★ Premium" : "Free"}</span>
);

export const money = (v: string | number) => `$${Number(v).toFixed(2)}`;
export const when = (iso: string) => new Date(iso).toLocaleString();
