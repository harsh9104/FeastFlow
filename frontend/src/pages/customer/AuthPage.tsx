import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../api";
import { useAuth } from "../../auth";
import { Alert } from "../../components/ui";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={user.role === "ADMIN" ? "/admin" : from ?? "/"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const u = mode === "login" ? await login(email, password) : await register(name, email, password);
      navigate(u.role === "ADMIN" ? "/admin" : from ?? "/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const isLogin = mode === "login";
  return (
    <div className="auth-card card">
      <h1>{isLogin ? "Welcome back" : "Create your account"}</h1>
      <p className="muted">
        {isLogin ? "Log in to order food or open the dispatch dashboard." : "Order from local restaurants in minutes."}
      </p>
      <form onSubmit={submit} className="form">
        {!isLogin && (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" />
          </label>
        )}
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={isLogin ? 1 : 8}
            autoComplete={isLogin ? "current-password" : "new-password"}
          />
          {!isLogin && <small className="muted">At least 8 characters.</small>}
        </label>
        <Alert>{error}</Alert>
        <button className="btn primary block" disabled={busy}>
          {busy ? "Please wait…" : isLogin ? "Log in" : "Sign up"}
        </button>
      </form>
      {!isLogin && (
        <p className="muted small-print">
          We'll email you a link to confirm order notifications. Click it to get order updates by email.
        </p>
      )}
      <p className="switch">
        {isLogin ? (
          <>New here? <Link to="/register" state={{ from }}>Create an account</Link></>
        ) : (
          <>Already have an account? <Link to="/login" state={{ from }}>Log in</Link></>
        )}
      </p>
    </div>
  );
}
