import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { MenuItem } from "../../api";
import { useAuth } from "../../auth";
import { useCart } from "../../cart";
import { CRAVINGS, coverImage, dishMatches, loadCatalog } from "../../catalog";
import { IconSearch } from "../../components/icons";
import { Alert, DishImage, Loading, RestaurantCard, VegMark } from "../../components/ui";
import { money } from "../../format";
import { usePolling } from "../../hooks";

export function Restaurants() {
  const { user } = useAuth();
  const cart = useCart();
  const { data, error, loading } = usePolling(() => loadCatalog(), null);
  const [query, setQuery] = useState("");
  const [craving, setCraving] = useState<string | null>(null);

  const terms = useMemo(() => {
    if (craving) return CRAVINGS.find((c) => c.label === craving)?.match ?? [];
    const q = query.trim().toLowerCase();
    return q ? [q] : [];
  }, [query, craving]);

  const { restaurants, dishes } = useMemo(() => {
    if (!data) return { restaurants: [], dishes: [] as { item: MenuItem; restaurant: string }[] };
    if (!terms.length) return { restaurants: data.restaurants, dishes: [] };
    const dishes = data.restaurants.flatMap((r) =>
      (data.menus[r.id] ?? [])
        .filter((i) => i.is_available && dishMatches(i, terms))
        .map((item) => ({ item, restaurant: r.name })),
    );
    const restaurantIds = new Set(dishes.map((d) => d.item.restaurant_id));
    const byName = data.restaurants.filter((r) =>
      terms.some((t) => `${r.name} ${r.cuisine} ${r.area}`.toLowerCase().includes(t)),
    );
    byName.forEach((r) => restaurantIds.add(r.id));
    return { restaurants: data.restaurants.filter((r) => restaurantIds.has(r.id)), dishes };
  }, [data, terms]);

  const firstName = user?.name.split(" ")[0];

  return (
    <>
      <section className="hero-banner">
        <div className="hero-copy">
          <span className="hero-kicker">{firstName ? `Hey ${firstName} 👋` : "Bengaluru's festival kitchen"}</span>
          <h1>
            Cravings delivered,
            <br />
            <span>hot &amp; fast.</span>
          </h1>
          <label className="hero-search">
            <IconSearch />
            <input
              placeholder="Search for biryani, dosa, pizza or a restaurant"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setCraving(null);
              }}
            />
          </label>
        </div>
        <div className="hero-art" aria-hidden>
          <span className="float f1">🍕</span>
          <span className="float f2">🍛</span>
          <span className="float f3">🍔</span>
          <span className="float f4">🥞</span>
          <span className="float f5">🍜</span>
          <span className="hero-plate">🍲</span>
        </div>
      </section>

      <section className="section">
        <h2 className="section-title">What's on your mind?</h2>
        <div className="cravings">
          {CRAVINGS.map((c) => (
            <button
              key={c.label}
              className={`craving${craving === c.label ? " active" : ""}`}
              onClick={() => {
                setCraving(craving === c.label ? null : c.label);
                setQuery("");
              }}
            >
              <span className="craving-icon">{c.emoji}</span>
              <span>{c.label}</span>
            </button>
          ))}
        </div>
      </section>

      {!terms.length && (
        <section className="promo-row">
          <Link to="/prime" className="promo promo-prime">
            <span className="promo-tag">FeastFlow Prime</span>
            <strong>{user?.is_prime ? "You're skipping the queue 👑" : "Skip the queue on busy nights"}</strong>
            <span>Prime orders are cooked and picked up first.</span>
          </Link>
          <div className="promo promo-festival">
            <span className="promo-tag">Festival season</span>
            <strong>Thousands of orders? We've got riders.</strong>
            <span>Live tracking from kitchen to door.</span>
          </div>
          <div className="promo promo-fresh">
            <span className="promo-tag">Freshly made</span>
            <strong>Local kitchens, cooked to order</strong>
            <span>Veg &amp; non-veg marked on every dish.</span>
          </div>
        </section>
      )}

      {loading && <Loading label="Finding restaurants near you…" />}
      <Alert>{error}</Alert>

      {dishes.length > 0 && (
        <section className="section">
          <h2 className="section-title">Dishes matching “{craving ?? query}”</h2>
          <div className="dish-strip">
            {dishes.slice(0, 12).map(({ item, restaurant }) => (
              <Link key={item.id} to={`/restaurants/${item.restaurant_id}`} className="dish-tile">
                <DishImage item={item} />
                <div>
                  <strong className="one-line"><VegMark veg={item.is_veg} /> {item.name}</strong>
                  <span className="muted one-line small">{restaurant}</span>
                  <span className="price">{money(item.price)}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {data && (
        <section className="section">
          <h2 className="section-title">
            {terms.length ? `${restaurants.length} restaurant${restaurants.length === 1 ? "" : "s"} found` : "Restaurants delivering to you"}
          </h2>
          {restaurants.length === 0 ? (
            <p className="muted">Nothing matches that. Try “paneer” or “coffee”.</p>
          ) : (
            <div className="rest-grid">
              {restaurants.map((r) => (
                <RestaurantCard key={r.id} restaurant={r} cover={coverImage(data.menus[r.id])} />
              ))}
            </div>
          )}
        </section>
      )}

      {cart.count > 0 && (
        <Link to="/cart" className="cart-bar">
          <span>
            {cart.count} item{cart.count > 1 ? "s" : ""} · {money(cart.total)}
            <small>from {cart.restaurantName}</small>
          </span>
          <strong>View cart →</strong>
        </Link>
      )}
    </>
  );
}
