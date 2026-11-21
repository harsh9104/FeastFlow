import { parseUtc } from "./api";
import type { OrderStatus } from "./api";

const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

export const money = (v: string | number) => rupees.format(Number(v));

// crypto.randomUUID only exists on secure pages (HTTPS or localhost); the AWS site is plain
// HTTP behind the ALB. getRandomValues works everywhere, so build a v4 UUID from it there.
export function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; // version 4
  b[8] = (b[8] & 0x3f) | 0x80; // RFC 4122 variant
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const time = (ts: string) =>
  parseUtc(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const dateTime = (ts: string) =>
  parseUtc(ts).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

export function ago(ts: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - parseUtc(ts).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export function seconds(v: number | null): string {
  if (v === null) return "–";
  return v < 60 ? `${v.toFixed(1)}s` : `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`;
}

export const STATUS_LABEL: Record<OrderStatus, string> = {
  PLACED: "Placed",
  CONFIRMED: "Confirmed",
  PREPARING: "Preparing",
  AWAITING_PARTNER: "Finding rider",
  OUT_FOR_DELIVERY: "On the way",
  DELIVERED: "Delivered",
  CANCELLED: "Cancelled",
};

/** The customer-facing steps, in order (AWAITING_PARTNER folds into "Preparing"). */
export const STEPS: OrderStatus[] = ["PLACED", "CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED"];

export const ACTIVE_STATUSES: OrderStatus[] = [
  "PLACED",
  "CONFIRMED",
  "PREPARING",
  "AWAITING_PARTNER",
  "OUT_FOR_DELIVERY",
];
