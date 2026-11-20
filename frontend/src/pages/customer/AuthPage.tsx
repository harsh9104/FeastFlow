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
    <div className="auth-wrap">
      <aside className="auth-art" aria-hidden>
        <div className="auth-emojis">
          <span>🍕</span><span>🍛</span><span>🍔</span><span>🥞</span><span>🍜</span><span>🍰</span>
        </div>
        <h2>Hungry? We've got you.</h2>
        <p>Order from the best local kitchens and track your rider live, right to your door.</p>
      </aside>
      <div className="auth-card card">
        <h1>{isLogin ? "Welcome back 👋" : "Create your account"}</h1>
        <p className="muted">
          {isLogin ? "Sign in to order food or open the dispatch dashboard." : "Join in seconds. Your first feast is waiting."}
        </p>
        <form onSubmit={submit} className="form">
          {!isLogin && (
            <label>
              Full name
              <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" placeholder="Asha Rao" />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" placeholder="you@example.com" />
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
              placeholder={isLogin ? "Your password" : "At least 8 characters"}
            />
          </label>
          <Alert>{error}</Alert>
          <button className="btn primary block large" disabled={busy}>
            {busy ? "Please wait…" : isLogin ? "Sign in" : "Create account"}
          </button>
        </form>
        {!isLogin && (
          <p className="muted small-print">
            We'll email you a link to confirm order updates. Click it to get notified when your food is on the way.
          </p>
        )}
        <p className="switch">
          {isLogin ? (
            <>New to FeastFlow? <Link to="/register" state={{ from }}>Create an account</Link></>
          ) : (
            <>Already have an account? <Link to="/login" state={{ from }}>Sign in</Link></>
          )}
        </p>
      </div>
    </div>
  );
}
