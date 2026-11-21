// Typed client for the FastAPI backend. Money arrives as strings (Python Decimal);
// timestamps arrive as UTC without a "Z", so parse them with parseUtc().

export type Role = "CUSTOMER" | "ADMIN";

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  is_prime: boolean;
  prime_expires_at: string | null;
  created_at?: string | null;
}

export interface TokenOut {
  access_token: string;
  user: User;
}

export interface Restaurant {
  id: number;
  name: string;
  area: string;
  cuisine: string;
  is_open: boolean;
  rating: string;
  delivery_minutes: number;
  cost_for_two: number;
  offer: string | null;
}

export interface MenuItem {
  id: number;
  restaurant_id: number;
  name: string;
  description: string | null;
  category: string;
  is_veg: boolean;
  price: string;
  is_available: boolean;
  is_bestseller: boolean;
  image_url: string | null;
}

export type OrderStatus =
  | "PLACED"
  | "CONFIRMED"
  | "PREPARING"
  | "AWAITING_PARTNER"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "CANCELLED";

export interface Order {
  id: number;
  status: OrderStatus;
  priority: number;
  is_prime: boolean;
  restaurant_id: number;
  restaurant_name: string;
  total_amount: string;
  delivery_address: string;
  created_at: string;
  customer_name: string | null;
  partner_name: string | null;
  partner_phone: string | null;
  items: { menu_item_id: number; name: string; quantity: number; unit_price: string }[];
  events: { status: OrderStatus; note: string | null; created_at: string }[];
}

export interface Page<T> {
  total: number;
  items: T[];
}

export interface Partner {
  id: number;
  name: string;
  phone: string;
  status: "AVAILABLE" | "BUSY" | "OFFLINE";
  deliveries_count: number;
  current_order_id: number | null;
}

export interface WaitSummary {
  orders: number;
  avg_seconds_to_confirm: number | null;
  avg_seconds_waiting_for_partner: number | null;
  avg_seconds_to_deliver: number | null;
}

export interface DispatchStats {
  queues: Record<"prime" | "standard", { waiting: number; in_flight: number } | null>;
  orders_by_status: Record<OrderStatus, number>;
  partners: Record<Partner["status"], number>;
  window_minutes: number;
  prime: WaitSummary;
  standard: WaitSummary;
}

const TOKEN_KEY = "feastflow.token";

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* private mode: stay logged in for this tab only */
    }
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// Called on any 401 so the app can drop the stale session (set by AuthProvider).
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{loc: [...], msg: "..."}]
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `Request failed (${status})`;
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = { ...options.headers };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) body = options.body;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let res: Response;
  try {
    res = await fetch(path, { method: options.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    throw new ApiError(res.status, errorMessage(data, res.status));
  }
  return data as T;
}

export function parseUtc(ts: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? ts : `${ts}Z`);
}

export interface FestivalRun {
  id: number;
  status: "RUNNING" | "COMPLETED" | "CANCELLED" | "FAILED";
  requested_orders: number;
  prime_percent: number;
  duration_seconds: number;
  created_orders: number;
  prime_orders: number;
  failed_orders: number;
  instance_id: string;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface LoadTestStatus {
  state: "ready" | "spawning" | "running" | "stopping" | "stopped" | string;
  users: number;
  rps: number;
  failures_per_second: number;
  fail_ratio: number;
  requests: number;
  failures: number;
  avg_ms: number;
  p50_ms: number | null;
  p95_ms: number | null;
  errors: { name: string; error: string; count: number }[];
}

// ---- admin Cloud & Cost panel ----
export type SectionError = { error: string };
export interface CloudInstance {
  id: string;
  az: string | null;
  type: string | null;
  lifecycle: string | null;
  health: string | null;
  launched_at: string | null;
}
export interface MetricPoint {
  t: string;
  v: number;
}
export interface CostLine {
  item: string;
  qty: number;
  unit_per_hour: number;
  per_hour: number;
  note: string;
}
export interface CloudOverview {
  configured: boolean;
  served_by: string;
  fetched_at?: string;
  asg?: SectionError | { name: string; min: number; max: number; desired: number; cpu_target: number | null; instances: CloudInstance[] };
  metrics?: SectionError | { cpu: MetricPoint[]; instances: MetricPoint[] };
  activities?: SectionError | { items: { at: string | null; description: string; status: string; cause: string }[] };
  alarms?: SectionError | { items: { name: string; state: string; reason: string; since: string | null; scaling: boolean }[] };
  cost?: { lines: CostLine[]; per_hour: number; per_day: number; per_month: number; unknown: string[]; note: string };
  budget?: SectionError | { name: string; limit: number | null; actual: number | null; forecast: number | null } | null;
}

export function sectionError(s: unknown): string | null {
  return s && typeof s === "object" && "error" in s ? (s as SectionError).error : null;
}
