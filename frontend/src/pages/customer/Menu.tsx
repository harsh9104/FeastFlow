import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { MenuItem, Order } from "../../api/types";
import { money } from "../../components/Badges";
import { useCart } from "../../context/CartContext";

export default function Menu() {
  const [items, setItems] = useState<MenuItem[]>([]);
  const [error, setError] = useState("");
  const cart = useCart();
  const nav = useNavigate();
  const [notes, setNotes] = useState("");
  const [placing, setPlacing] = useState(false);
  const [orderError, setOrderError] = useState("");

  useEffect(() => {
    api<MenuItem[]>("/menu")
      .then(setItems)
      .catch((e) => setError(e.message));
  }, []);

  async function place() {
    setPlacing(true);
    setOrderError("");
    try {
      const o = await api<Order>("/orders", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: {
          items: cart.lines.map((l) => ({ menu_item_id: l.item.id, quantity: l.quantity })),
          notes: notes.trim() || undefined,
        },
      });
      cart.clear();
      setNotes("");
      nav(`/orders?placed=${o.id}`);
    } catch (e) {
      setOrderError((e as Error).message);
    } finally {
      setPlacing(false);
    }
  }

  const categories = [...new Set(items.map((i) => i.category))];

  return (
    <div className="split">
      <section>
        <h1>Menu</h1>
        {error && <p className="error">{error}</p>}
        {categories.map((c) => (
          <div key={c}>
            <h2>{c}</h2>
            <div className="grid">
              {items
                .filter((i) => i.category === c)
                .map((i) => (
                  <article key={i.id} className="card item">
                    {i.image_url && <img src={i.image_url} alt={i.name}
                        loading="lazy"
                        onError={(e) => (e.currentTarget.style.display = "none")}
                      />}
                    <h3>{i.name}</h3>
                    <p className="muted">{i.description}</p>
                    <div className="row">
                      <strong>{money(i.price)}</strong>
                      <button className="btn small primary" disabled={!i.is_available} onClick={() => cart.add(i)}>
                        {i.is_available ? "Add" : "Sold out"}
                      </button>
                    </div>
                  </article>
                ))}
            </div>
          </div>
        ))}
      </section>

      <aside className="card cart">
        <h2>Your order</h2>
        {cart.lines.length === 0 && <p className="muted">Your cart is empty.</p>}
        {cart.lines.map((l) => (
          <div key={l.item.id} className="cartline">
            <span>{l.item.name}</span>
            <span className="qty">
              <button className="btn small" onClick={() => cart.setQty(l.item.id, l.quantity - 1)} aria-label="Decrease">
                −
              </button>
              {l.quantity}
              <button className="btn small" onClick={() => cart.setQty(l.item.id, l.quantity + 1)} aria-label="Increase">
                +
              </button>
            </span>
            <span>{money(Number(l.item.price) * l.quantity)}</span>
          </div>
        ))}
        {cart.lines.length > 0 && (
          <>
            <textarea
              placeholder="Notes (optional)"
              maxLength={500}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <div className="row total">
              <span>Total</span>
              <strong>{money(cart.total)}</strong>
            </div>
            {orderError && <p className="error">{orderError}</p>}
            <button className="btn primary block" disabled={placing} onClick={place}>
              {placing ? "Placing…" : "Place order"}
            </button>
          </>
        )}
      </aside>
    </div>
  );
}
