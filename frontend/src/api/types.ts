export type Tier = "FREE" | "PREMIUM";
export type Role = "CUSTOMER" | "ADMIN";
export type OrderStatus = "PENDING" | "PREPARING" | "COMPLETED";

export interface User {
  id: number;
  full_name: string;
  email: string;
  role: Role;
  subscription_tier: Tier;
}

export interface MenuItem {
  id: number;
  name: string;
  description: string | null;
  category: string;
  price: string;
  image_url: string | null;
  is_available: boolean;
}

export interface OrderItem {
  menu_item_id: number;
  name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface Order {
  id: number;
  status: OrderStatus;
  priority: number;
  tier_at_order: Tier;
  total_amount: string;
  notes: string | null;
  version: number;
  created_at: string;
  items: OrderItem[];
  customer?: string;
}

export interface HistoryEntry {
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  changed_at: string;
}

export interface OrderDetail extends Order {
  history: HistoryEntry[];
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface Stats {
  counts_by_status: Record<OrderStatus, number>;
  avg_wait_premium_s: number | null;
  avg_wait_free_s: number | null;
}
