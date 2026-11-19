import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, parseUtc } from "../../api";
import type { TokenOut } from "../../api";
import { useAuth } from "../../auth";
import { Alert, PrimeBadge } from "../../components/ui";

const PERKS = [
  ["⚡", "Priority kitchen queue", "Your order is picked up before standard orders."],
  ["🛵", "First pick of riders", "When food is ready, a free delivery partner goes to you first."],
  ["🎉", "Festival-day protection", "Stay fast even when the whole city is ordering."],
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
      setMessage(path === "subscribe" ? "You're Prime! Your next order is prioritised." : "Prime cancelled.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const expires = user?.prime_expires_at ? parseUtc(user.prime_expires_at) : null;

  return (
    <div className="prime-page">
      <section className="prime-hero card">
        <PrimeBadge />
        <h1>Skip the queue with FeastFlow Prime</h1>
        <p className="price">₹99 <span className="muted">/ 30 days</span></p>
        <p className="muted small-print">Demo project: no real payment is taken.</p>

        {!user ? (
          <Link to="/login" state={{ from: "/prime" }} className="btn primary">Log in to join</Link>
        ) : user.role === "ADMIN" ? (
          <Alert kind="info">Admins can't subscribe.</Alert>
        ) : user.is_prime ? (
          <div className="prime-active">
            <p>
              You're a Prime member until <strong>{expires?.toLocaleDateString([], { dateStyle: "long" })}</strong>.
            </p>
            <div className="row">
              <button className="btn primary" disabled={busy} onClick={() => act("subscribe")}>Add 30 more days</button>
              <button className="btn ghost" disabled={busy} onClick={() => act("cancel")}>Cancel Prime</button>
            </div>
          </div>
        ) : (
          <button className="btn primary large" disabled={busy} onClick={() => act("subscribe")}>
            {busy ? "Activating…" : "Join Prime"}
          </button>
        )}
        <Alert kind="success">{message}</Alert>
        <Alert>{error}</Alert>
      </section>

      <div className="grid perks">
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
