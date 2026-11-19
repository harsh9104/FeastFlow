import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import type { MenuItem, Restaurant } from "../../api";
import { useAuth } from "../../auth";
import { useCart } from "../../cart";
import { Alert, Loading, VegMark } from "../../components/ui";
import { money } from "../../format";
import { usePolling } from "../../hooks";

export function MenuPage() {
  const id = Number(useParams().id);
  const { user } = useAuth();
  const cart = useCart();
  const { data, error, loading } = usePolling(
    async () => {
      const [restaurants, menu] = await Promise.all([
        api<Restaurant[]>("/api/restaurants"),
        api<MenuItem[]>(`/api/restaurants/${id}/menu`),
      ]);
      return { restaurant: restaurants.find((r) => r.id === id) ?? null, menu };
    },
    null,
    [id],
  );

  const byCategory = useMemo(() => {
    const groups = new Map<string, MenuItem[]>();
    for (const item of data?.menu ?? []) {
      groups.set(item.category, [...(groups.get(item.category) ?? []), item]);
    }
    return [...groups.entries()];
  }, [data]);

  if (loading) return <Loading />;
  if (error || !data?.restaurant) return <Alert>{error ?? "Restaurant not found"}</Alert>;
  const { restaurant } = data;
  const qtyInCart = (itemId: number) => cart.lines.find((l) => l.item.id === itemId)?.quantity ?? 0;
  const isAdmin = user?.role === "ADMIN";

  return (
    <>
      <Link to="/" className="back">← All restaurants</Link>
      <header className="section-head">
        <div>
          <h1>{restaurant.name}</h1>
          <p className="muted">{restaurant.cuisine} · {restaurant.area}</p>
        </div>
      </header>
      {!restaurant.is_open && <Alert kind="info">This restaurant is closed right now.</Alert>}

      {byCategory.map(([category, items]) => (
        <section key={category} className="menu-section">
          <h2>{category}</h2>
          <div className="grid menu">
            {items.map((item) => {
              const qty = qtyInCart(item.id);
              const disabled = !item.is_available || !restaurant.is_open || isAdmin;
              return (
                <article key={item.id} className={`card dish${item.is_available ? "" : " unavailable"}`}>
                  <div className="dish-img">
                    {item.image_url ? <img src={item.image_url} alt={item.name} loading="lazy" /> : <span aria-hidden>🍽️</span>}
                  </div>
                  <div className="dish-body">
                    <h3><VegMark veg={item.is_veg} /> {item.name}</h3>
                    {item.description && <p className="muted">{item.description}</p>}
                    <div className="dish-foot">
                      <strong>{money(item.price)}</strong>
                      {!item.is_available ? (
                        <span className="muted">Sold out</span>
                      ) : qty > 0 ? (
                        <div className="stepper">
                          <button onClick={() => cart.setQuantity(item.id, qty - 1)} aria-label={`Remove one ${item.name}`}>−</button>
                          <span>{qty}</span>
                          <button onClick={() => cart.add(item, restaurant.name)} aria-label={`Add one ${item.name}`}>+</button>
                        </div>
                      ) : (
                        <button className="btn small" disabled={disabled} onClick={() => cart.add(item, restaurant.name)}>
                          Add
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}

      {cart.count > 0 && cart.restaurantId === id && (
        <Link to="/cart" className="cart-bar">
          <span>{cart.count} item{cart.count > 1 ? "s" : ""} · {money(cart.total)}</span>
          <strong>View cart →</strong>
        </Link>
      )}
    </>
  );
}
