import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../../api";
import type { Order } from "../../api";
import { useAuth } from "../../auth";
import { useCart } from "../../cart";
import { Alert, Empty, PrimeBadge, VegMark } from "../../components/ui";
import { money } from "../../format";

const ADDRESS_KEY = "feastflow.address";

function savedAddress(): string {
  try {
    return localStorage.getItem(ADDRESS_KEY) ?? "";
  } catch {
    return "";
  }
}

export function Cart() {
  const cart = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [address, setAddress] = useState(savedAddress);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Same key for every retry of this checkout, so a double-click or a retry after a
  // network error can never create two orders. A new key only after success.
  const idemKey = useRef<string>(crypto.randomUUID());

  if (cart.count === 0) {
    return (
      <Empty>
        <p>Your cart is empty.</p>
        <Link to="/" className="btn primary">Browse restaurants</Link>
      </Empty>
    );
  }

  async function checkout(e: FormEvent) {
    e.preventDefault();
    if (!user) {
      navigate("/login", { state: { from: "/cart" } });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const order = await api<Order>("/api/orders", {
        method: "POST",
        headers: { "Idempotency-Key": idemKey.current },
        body: {
          items: cart.lines.map((l) => ({ menu_item_id: l.item.id, quantity: l.quantity })),
          delivery_address: address,
        },
      });
      try {
        localStorage.setItem(ADDRESS_KEY, address);
      } catch {
        /* not essential */
      }
      cart.clear();
      idemKey.current = crypto.randomUUID();
      navigate(`/orders/${order.id}`, { state: { justPlaced: true } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't place the order");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="checkout">
      <section className="card">
        <h1>Your order</h1>
        <p className="muted">From {cart.restaurantName}</p>
        <ul className="cart-lines">
          {cart.lines.map(({ item, quantity }) => (
            <li key={item.id}>
              <span className="name"><VegMark veg={item.is_veg} /> {item.name}</span>
              <div className="stepper">
                <button onClick={() => cart.setQuantity(item.id, quantity - 1)} aria-label={`Remove one ${item.name}`}>−</button>
                <span>{quantity}</span>
                <button onClick={() => cart.setQuantity(item.id, quantity + 1)} aria-label={`Add one ${item.name}`}>+</button>
              </div>
              <span className="amount">{money(Number(item.price) * quantity)}</span>
            </li>
          ))}
        </ul>
        <div className="total-row">
          <span>Total</span>
          <strong>{money(cart.total)}</strong>
        </div>
        <p className="muted small-print">Final prices are confirmed by the restaurant when you place the order.</p>
      </section>

      <form className="card form" onSubmit={checkout}>
        <h2>Delivery</h2>
        <label>
          Address
          <textarea
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            required
            minLength={5}
            maxLength={255}
            rows={3}
            placeholder="House no., street, area, city"
          />
        </label>
        {user?.is_prime ? (
          <div className="prime-note">
            <PrimeBadge /> Your order goes to the front of the queue.
          </div>
        ) : user ? (
          <div className="prime-note muted">
            Busy day? <Link to="/prime">Prime members</Link> are served first.
          </div>
        ) : null}
        <Alert>{error}</Alert>
        <button className="btn primary block" disabled={busy || user?.role === "ADMIN"}>
          {busy ? "Placing order…" : user ? `Place order · ${money(cart.total)}` : "Log in to place order"}
        </button>
      </form>
    </div>
  );
}
