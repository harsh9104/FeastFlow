// Restaurants + menus, shared by the home page, menu page and admin menu.
// Small data set (a few restaurants), so it's loaded in one go and cached briefly.
import { api } from "./api";
import type { MenuItem, Restaurant } from "./api";

export interface Catalog {
  restaurants: Restaurant[];
  menus: Record<number, MenuItem[]>;
}

let cache: { at: number; data: Catalog } | null = null;
const TTL_MS = 30_000;

export async function loadCatalog(force = false): Promise<Catalog> {
  if (!force && cache && Date.now() - cache.at < TTL_MS) return cache.data;
  const restaurants = await api<Restaurant[]>("/api/restaurants");
  const lists = await Promise.all(restaurants.map((r) => api<MenuItem[]>(`/api/restaurants/${r.id}/menu`)));
  const data: Catalog = {
    restaurants,
    menus: Object.fromEntries(restaurants.map((r, i) => [r.id, lists[i]])),
  };
  cache = { at: Date.now(), data };
  return data;
}

export function invalidateCatalog() {
  cache = null;
}

/** Cover picture for a restaurant: its bestseller's photo, else any dish photo. */
export function coverImage(items: MenuItem[] | undefined): string | null {
  if (!items?.length) return null;
  return (items.find((i) => i.is_bestseller && i.image_url) ?? items.find((i) => i.image_url))?.image_url ?? null;
}

export const CUISINE_EMOJI: Record<string, string> = {
  "North Indian": "🍛",
  "South Indian": "🥞",
  Chinese: "🥡",
  "Pizza & Fast Food": "🍕",
};

/** "What's on your mind?" shortcuts: matched against dish names and categories. */
export const CRAVINGS = [
  { label: "Biryani", emoji: "🍛", match: ["biryani"] },
  { label: "Dosa", emoji: "🥞", match: ["dosa", "idli", "vada"] },
  { label: "Pizza", emoji: "🍕", match: ["pizza"] },
  { label: "Burger", emoji: "🍔", match: ["burger", "fries"] },
  { label: "Noodles", emoji: "🍜", match: ["noodle", "hakka", "fried rice", "manchurian"] },
  { label: "Paneer", emoji: "🧀", match: ["paneer"] },
  { label: "Desserts", emoji: "🍨", match: ["dessert", "jamun", "kulfi", "shake"] },
  { label: "Coffee", emoji: "☕", match: ["coffee", "beverage"] },
];

export function dishMatches(item: MenuItem, terms: string[]): boolean {
  const text = `${item.name} ${item.category} ${item.description ?? ""}`.toLowerCase();
  return terms.some((t) => text.includes(t));
}
