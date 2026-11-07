import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import type { Tier } from "../../api/types";

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const u = await login(email, password);
      nav(u.role === "ADMIN" ? "/admin/queue" : "/menu", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card auth" onSubmit={submit}>
      <h1>Sign in</h1>
      <label>
        Email
        <input value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="btn primary" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <p className="muted">
        New here? <Link to="/register">Create an account</Link>
      </p>
    </form>
  );
}

export function Register() {
  const { register, login } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [tier, setTier] = useState<Tier>("FREE");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await register(form.full_name, form.email, form.password, tier);
      await login(form.email, form.password);
      nav("/menu", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card auth" onSubmit={submit}>
      <h1>Create account</h1>
      <label>
        Full name
        <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
      </label>
      <label>
        Email
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      </label>
      <label>
        Password (min 8 characters)
        <input
          type="password"
          minLength={8}
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          required
        />
      </label>
      <fieldset>
        <legend>Plan (simulated, no payment)</legend>
        <label className="radio">
          <input type="radio" checked={tier === "FREE"} onChange={() => setTier("FREE")} /> Free
        </label>
        <label className="radio">
          <input type="radio" checked={tier === "PREMIUM"} onChange={() => setTier("PREMIUM")} /> ★ Premium
          (orders are prepared first)
        </label>
      </fieldset>
      {error && <p className="error">{error}</p>}
      <button className="btn primary" disabled={busy}>
        {busy ? "Creating…" : "Create account"}
      </button>
      <p className="muted">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </form>
  );
}
