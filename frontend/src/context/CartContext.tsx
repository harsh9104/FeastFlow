import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { MenuItem } from "../api/types";

export interface CartLine {
  item: MenuItem;
  quantity: number;
}

interface CartState {
  lines: CartLine[];
  count: number;
  total: number;
  add: (item: MenuItem) => void;
  setQty: (id: number, qty: number) => void;
  clear: () => void;
}

const Ctx = createContext<CartState | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);

  const value = useMemo<CartState>(
    () => ({
      lines,
      count: lines.reduce((n, l) => n + l.quantity, 0),
      // Display only. The server recomputes the real total from DB prices.
      total: lines.reduce((s, l) => s + Number(l.item.price) * l.quantity, 0),
      add: (item) =>
        setLines((cur) => {
          const found = cur.find((l) => l.item.id === item.id);
          if (!found) return [...cur, { item, quantity: 1 }];
          return cur.map((l) =>
            l.item.id === item.id ? { ...l, quantity: Math.min(20, l.quantity + 1) } : l,
          );
        }),
      setQty: (id, qty) =>
        setLines((cur) =>
          qty <= 0
            ? cur.filter((l) => l.item.id !== id)
            : cur.map((l) => (l.item.id === id ? { ...l, quantity: Math.min(20, qty) } : l)),
        ),
      clear: () => setLines([]),
    }),
    [lines],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCart outside CartProvider");
  return v;
}
