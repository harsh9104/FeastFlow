import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, parseUtc } from "../../api";
import type { TokenOut } from "../../api";
import { useAuth } from "../../auth";
import { Alert } from "../../components/ui";

const PERKS = [
  ["⚡", "Priority kitchen queue", "Your order is cooked before standard orders, every time."],
  ["🛵", "First pick of riders", "When your food is ready, the next free rider comes to you."],
  ["🎆", "Festival-night protection", "Stay fast even when the whole city is ordering at once."],
  ["🏷️", "Members-only offers", "Extra savings at partner restaurants (coming soon)."],
];

export function Prime() {
  const { user, applyToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function act(path: "subscribe" | "cancel") {
    if (path === "cancel" && !window.confirm("Cancel Prime now? Priority ends immediately.")) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const t = await api<TokenOut>(`/api/prime/${path}`, { method: "POST" });
      applyToken(t);
      setMessage(path === "subscribe" ? "Welcome to Prime 👑 Your next order skips the queue." : "Prime cancelled.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const expires = user?.prime_expires_at ? parseUtc(user.prime_expires_at) : null;

  return (
    <div className="prime-page">
      <section className="prime-hero">
        <div className="prime-copy">
          <span className="prime-chip">👑 FeastFlow Prime</span>
          <h1>Never wait in the festival rush again.</h1>
          <p>Prime orders go to the front of the kitchen queue and get the first free delivery partner.</p>

          <div className="prime-price">
            <strong>₹99</strong>
            <span>for 30 days</span>
          </div>

          {!user ? (
            <Link to="/login" state={{ from: "/prime" }} className="btn gold large">Sign in to join</Link>
          ) : user.role === "ADMIN" ? (
            <Alert kind="info">Admins can't subscribe.</Alert>
          ) : user.is_prime ? (
            <div className="prime-active">
              <p>
                You're a member until <strong>{expires?.toLocaleDateString([], { dateStyle: "long" })}</strong>.
              </p>
              <div className="row">
                <button className="btn gold" disabled={busy} onClick={() => act("subscribe")}>Add 30 more days</button>
                <button className="btn ghost-light" disabled={busy} onClick={() => act("cancel")}>Cancel Prime</button>
              </div>
            </div>
          ) : (
            <button className="btn gold large" disabled={busy} onClick={() => act("subscribe")}>
              {busy ? "Activating…" : "Join Prime for ₹99"}
            </button>
          )}
          <p className="prime-fine">Demo project: no real payment is taken.</p>
          <Alert kind="success">{message}</Alert>
          <Alert>{error}</Alert>
        </div>
        <div className="prime-art" aria-hidden>
          <span className="prime-crown">👑</span>
          <span className="float f1">🍔</span>
          <span className="float f2">🍕</span>
          <span className="float f3">🍛</span>
        </div>
      </section>

      <div className="perks">
        {PERKS.map(([icon, title, text]) => (
          <div key={title} className="card perk">
            <span className="perk-icon" aria-hidden>{icon}</span>
            <h3>{title}</h3>
            <p className="muted">{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
