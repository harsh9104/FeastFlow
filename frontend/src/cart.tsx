import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { MenuItem } from "./api";

// One restaurant per order (the backend enforces this too), so adding an item from
// another restaurant asks to replace the cart.

export interface CartLine {
  item: MenuItem;
  quantity: number;
}

interface CartState {
  restaurantId: number | null;
  restaurantName: string | null;
  lines: CartLine[];
  count: number;
  total: number;
  add: (item: MenuItem, restaurantName: string) => boolean;
  setQuantity: (itemId: number, quantity: number) => void;
  clear: () => void;
}

const KEY = "feastflow.cart";
const MAX_QTY = 20;

interface Stored {
  restaurantId: number | null;
  restaurantName: string | null;
  lines: CartLine[];
}

const EMPTY: Stored = { restaurantId: null, restaurantName: null, lines: [] };

function load(): Stored {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Stored) : EMPTY;
  } catch {
    return EMPTY;
  }
}

const CartContext = createContext<CartState | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Stored>(load);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(cart));
    } catch {
      /* storage unavailable: cart lives for this tab only */
    }
  }, [cart]);

  const value = useMemo<CartState>(() => {
    const count = cart.lines.reduce((n, l) => n + l.quantity, 0);
    const total = cart.lines.reduce((n, l) => n + Number(l.item.price) * l.quantity, 0);
    return {
      ...cart,
      count,
      total,
      add(item, restaurantName) {
        if (cart.restaurantId !== null && cart.restaurantId !== item.restaurant_id) {
          const ok = window.confirm(
            `Your cart has items from ${cart.restaurantName}. Start a new cart from ${restaurantName}?`,
          );
          if (!ok) return false;
          setCart({ restaurantId: item.restaurant_id, restaurantName, lines: [{ item, quantity: 1 }] });
          return true;
        }
        setCart((c) => {
          const existing = c.lines.find((l) => l.item.id === item.id);
          const lines = existing
            ? c.lines.map((l) =>
                l.item.id === item.id ? { ...l, quantity: Math.min(MAX_QTY, l.quantity + 1) } : l,
              )
            : [...c.lines, { item, quantity: 1 }];
          return { restaurantId: item.restaurant_id, restaurantName, lines };
        });
        return true;
      },
      setQuantity(itemId, quantity) {
        setCart((c) => {
          const lines = c.lines
            .map((l) => (l.item.id === itemId ? { ...l, quantity: Math.min(MAX_QTY, quantity) } : l))
            .filter((l) => l.quantity > 0);
          return lines.length ? { ...c, lines } : EMPTY;
        });
      },
      clear() {
        setCart(EMPTY);
      },
    };
  }, [cart]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartState {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart outside CartProvider");
  return ctx;
}
