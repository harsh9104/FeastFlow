import { Link } from "react-router-dom";
import { api } from "../../api";
import type { Restaurant } from "../../api";
import { useAuth } from "../../auth";
import { Alert, Loading } from "../../components/ui";
import { usePolling } from "../../hooks";

const CUISINE_EMOJI: Record<string, string> = {
  "North Indian": "🍛",
  "South Indian": "🥞",
  Chinese: "🥡",
  "Pizza & Fast Food": "🍕",
};

export function Restaurants() {
  const { user } = useAuth();
  const { data, error, loading } = usePolling(() => api<Restaurant[]>("/api/restaurants"), null);

  return (
    <>
      <section className="hero">
        <div>
          <h1>Hungry{user ? `, ${user.name.split(" ")[0]}` : ""}?</h1>
          <p className="muted">Pick a restaurant and we'll have it at your door.</p>
        </div>
        {!user?.is_prime && (
          <Link to="/prime" className="prime-cta">
            <strong>★ Get Prime</strong>
            <span>Your orders are cooked and delivered first, even on festival days.</span>
          </Link>
        )}
      </section>
      {loading && <Loading />}
      <Alert>{error}</Alert>
      <div className="grid restaurants">
        {data?.map((r) => (
          <Link key={r.id} to={`/restaurants/${r.id}`} className={`card restaurant${r.is_open ? "" : " closed"}`}>
            <div className="restaurant-art" aria-hidden>
              {CUISINE_EMOJI[r.cuisine] ?? "🍽️"}
            </div>
            <div className="restaurant-body">
              <h3>{r.name}</h3>
              <p className="muted">
                {r.cuisine} · {r.area}
              </p>
              {!r.is_open && <span className="badge status-cancelled">Closed</span>}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
