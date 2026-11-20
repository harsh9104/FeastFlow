import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { MenuItem } from "../../api";
import { useAuth } from "../../auth";
import { useCart } from "../../cart";
import { CUISINE_EMOJI, coverImage, loadCatalog } from "../../catalog";
import { IconClock, IconSearch } from "../../components/icons";
import { Alert, DishImage, Loading, Rating, VegMark } from "../../components/ui";
import { money } from "../../format";
import { usePolling } from "../../hooks";

export function MenuPage() {
  const id = Number(useParams().id);
  const { user } = useAuth();
  const cart = useCart();
  const { data, error, loading } = usePolling(() => loadCatalog(true), null, [id]);
  const [vegOnly, setVegOnly] = useState(false);
  const [query, setQuery] = useState("");

  const restaurant = data?.restaurants.find((r) => r.id === id) ?? null;
  const menu = useMemo(() => data?.menus[id] ?? [], [data, id]);

  const byCategory = useMemo(() => {
    const q = query.trim().toLowerCase();
    const groups = new Map<string, MenuItem[]>();
    const bestsellers = menu.filter((i) => i.is_bestseller && (!vegOnly || i.is_veg));
    if (!q && bestsellers.length) groups.set("Bestsellers", bestsellers);
    for (const item of menu) {
      if (vegOnly && !item.is_veg) continue;
      if (q && !`${item.name} ${item.description ?? ""}`.toLowerCase().includes(q)) continue;
      groups.set(item.category, [...(groups.get(item.category) ?? []), item]);
    }
    return [...groups.entries()];
  }, [menu, vegOnly, query]);

  if (loading) return <Loading label="Opening the menu…" />;
  if (error || !restaurant) return <Alert>{error ?? "Restaurant not found"}</Alert>;

  const qtyInCart = (itemId: number) => cart.lines.find((l) => l.item.id === itemId)?.quantity ?? 0;
  const isAdmin = user?.role === "ADMIN";
  const cover = coverImage(menu);
  const slug = (s: string) => `cat-${s.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="menu-page">
      <nav className="crumbs">
        <Link to="/">Home</Link> / <span>{restaurant.name}</span>
      </nav>

      <section className="rest-hero">
        <div className="rest-hero-img">
          {cover ? <img src={cover} alt="" /> : <span>{CUISINE_EMOJI[restaurant.cuisine] ?? "🍽️"}</span>}
        </div>
        <div className="rest-hero-info">
          <h1>{restaurant.name}</h1>
          <p className="muted">{restaurant.cuisine} · {restaurant.area}</p>
          <div className="rest-stats">
            <div><Rating value={restaurant.rating} /><small>1K+ ratings</small></div>
            <div><strong><IconClock /> {restaurant.delivery_minutes} mins</strong><small>Delivery time</small></div>
            <div><strong>₹{restaurant.cost_for_two}</strong><small>Cost for two</small></div>
          </div>
          {restaurant.offer && <div className="offer-ticket">🏷️ {restaurant.offer}</div>}
        </div>
      </section>

      {!restaurant.is_open && <Alert kind="info">This restaurant is closed right now. You can still look around.</Alert>}
      {isAdmin && <Alert kind="info">You're signed in as admin, so ordering is off here.</Alert>}

      <div className="menu-tools">
        <label className="menu-search">
          <IconSearch />
          <input placeholder="Search in menu" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <button className={`veg-toggle${vegOnly ? " on" : ""}`} onClick={() => setVegOnly(!vegOnly)} aria-pressed={vegOnly}>
          <span className="switch-track"><span className="switch-thumb" /></span>
          Veg only
        </button>
      </div>

      <div className="menu-layout">
        <aside className="cat-nav">
          {byCategory.map(([c, items]) => (
            <a key={c} href={`#${slug(c)}`}>
              {c} <span>{items.length}</span>
            </a>
          ))}
        </aside>

        <div className="menu-list">
          {byCategory.length === 0 && <p className="muted">No dishes match.</p>}
          {byCategory.map(([category, items]) => (
            <section key={category} id={slug(category)} className="menu-section">
              <h2>{category} <span className="muted">({items.length})</span></h2>
              {items.map((item) => {
                const qty = qtyInCart(item.id);
                const canOrder = item.is_available && restaurant.is_open && !isAdmin;
                return (
                  <article key={`${category}-${item.id}`} className={`dish-row${item.is_available ? "" : " sold-out"}`}>
                    <div className="dish-info">
                      <div className="dish-tags">
                        <VegMark veg={item.is_veg} />
                        {item.is_bestseller && <span className="bestseller">★ Bestseller</span>}
                      </div>
                      <h3>{item.name}</h3>
                      <p className="dish-price">{money(item.price)}</p>
                      {item.description && <p className="muted dish-desc">{item.description}</p>}
                    </div>
                    <div className="dish-media">
                      <DishImage item={item} />
                      {!item.is_available ? (
                        <span className="add-btn disabled">Sold out</span>
                      ) : qty > 0 ? (
                        <div className="add-btn stepper-btn">
                          <button onClick={() => cart.setQuantity(item.id, qty - 1)} aria-label={`Remove one ${item.name}`}>−</button>
                          <span>{qty}</span>
                          <button onClick={() => cart.add(item, restaurant.name)} aria-label={`Add one ${item.name}`}>+</button>
                        </div>
                      ) : (
                        <button className="add-btn" disabled={!canOrder} onClick={() => cart.add(item, restaurant.name)}>
                          ADD
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </section>
          ))}
        </div>
      </div>

      {cart.count > 0 && cart.restaurantId === id && (
        <Link to="/cart" className="cart-bar">
          <span>
            {cart.count} item{cart.count > 1 ? "s" : ""} added · {money(cart.total)}
          </span>
          <strong>View cart 🛍️</strong>
        </Link>
      )}
    </div>
  );
}
