import { useState } from "react";
import type { Tier } from "../../api/types";
import { PriorityBadge } from "../../components/Badges";
import { useAuth } from "../../context/AuthContext";

export default function Profile() {
  const { user, setTier } = useAuth();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  async function change(t: Tier) {
    setBusy(true);
    setMsg("");
    try {
      await setTier(t);
      setMsg(`Plan changed to ${t}. It applies to orders you place from now on.`);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const target: Tier = user.subscription_tier === "FREE" ? "PREMIUM" : "FREE";
  return (
    <section className="card auth">
      <h1>Profile</h1>
      <p>
        <strong>{user.full_name}</strong>
        <br />
        <span className="muted">{user.email}</span>
      </p>
      <p>
        Current plan: <PriorityBadge tier={user.subscription_tier} />
      </p>
      <p className="muted">Subscription is simulated (no payment). Premium orders are prepared first.</p>
      <button className="btn primary" disabled={busy} onClick={() => change(target)}>
        Switch to {target === "PREMIUM" ? "★ Premium" : "Free"}
      </button>
      {msg && <p className="success">{msg}</p>}
    </section>
  );
}
