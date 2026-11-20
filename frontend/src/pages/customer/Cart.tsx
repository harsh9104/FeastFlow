import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../../api";
import type { Order } from "../../api";
import { useAuth } from "../../auth";
import { useCart } from "../../cart";
import { IconPin } from "../../components/icons";
import { Alert, DishImage, Empty, VegMark } from "../../components/ui";
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
      <Empty icon="🛍️">
        <h2>Your cart is empty</h2>
        <p className="muted">Good food is always cooking. Go ahead, order some yummy items from the menu.</p>
        <Link to="/" className="btn primary">See restaurants near you</Link>
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
      <form className="checkout-main" onSubmit={checkout} id="checkout">
        <section className="card step-card">
          <span className="step-no">1</span>
          <div className="step-body">
            <h2><IconPin /> Delivery address</h2>
            <textarea
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              required
              minLength={5}
              maxLength={255}
              rows={3}
              placeholder="Flat / house no., street, landmark, area"
            />
          </div>
        </section>

        <section className="card step-card">
          <span className="step-no">2</span>
          <div className="step-body">
            <h2>Delivery speed</h2>
            {user?.is_prime ? (
              <div className="speed prime-on">
                <span className="speed-icon">👑</span>
                <div>
                  <strong>Prime priority is on</strong>
                  <p className="muted">Your order jumps the kitchen queue and gets the first free rider.</p>
                </div>
              </div>
            ) : (
              <div className="speed">
                <span className="speed-icon">🛵</span>
                <div>
                  <strong>Standard delivery</strong>
                  <p className="muted">
                    Busy night? <Link to="/prime">Join Prime</Link> and skip the queue.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="card step-card">
          <span className="step-no">3</span>
          <div className="step-body">
            <h2>Payment</h2>
            <p className="muted">Cash on delivery. This is a demo, so no real payment is taken.</p>
          </div>
        </section>
      </form>

      <aside className="card bill">
        <header className="bill-head">
          <span className="bill-emoji">🍽️</span>
          <div>
            <strong>{cart.restaurantName}</strong>
            <small className="muted">{cart.count} item{cart.count > 1 ? "s" : ""}</small>
          </div>
        </header>
        <ul className="bill-lines">
          {cart.lines.map(({ item, quantity }) => (
            <li key={item.id}>
              <DishImage item={item} className="mini" />
              <span className="name"><VegMark veg={item.is_veg} /> {item.name}</span>
              <div className="qty">
                <button type="button" onClick={() => cart.setQuantity(item.id, quantity - 1)} aria-label={`Remove one ${item.name}`}>−</button>
                <span>{quantity}</span>
                <button type="button" onClick={() => cart.setQuantity(item.id, quantity + 1)} aria-label={`Add one ${item.name}`}>+</button>
              </div>
              <span className="amount">{money(Number(item.price) * quantity)}</span>
            </li>
          ))}
        </ul>
        <div className="bill-details">
          <h3>Bill details</h3>
          <div><span>Item total</span><span>{money(cart.total)}</span></div>
          <div><span>Delivery fee</span><span className="free">FREE</span></div>
          <div className="to-pay"><span>To pay</span><strong>{money(cart.total)}</strong></div>
        </div>
        <Alert>{error}</Alert>
        <button className="btn primary block large" form="checkout" disabled={busy || user?.role === "ADMIN"}>
          {busy ? "Placing order…" : user ? `Place order · ${money(cart.total)}` : "Sign in to place order"}
        </button>
        <p className="muted small-print">Prices are re-checked by the restaurant when you place the order.</p>
      </aside>
    </div>
  );
}
