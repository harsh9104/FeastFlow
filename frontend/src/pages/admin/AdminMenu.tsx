import { useState } from "react";
import { ApiError, api } from "../../api";
import type { MenuItem, Restaurant } from "../../api";
import { Alert, Loading, VegMark } from "../../components/ui";
import { money } from "../../format";
import { usePolling } from "../../hooks";

export function AdminMenu() {
  const { data, error, loading, setData } = usePolling(async () => {
    const restaurants = await api<Restaurant[]>("/api/restaurants");
    const menus = await Promise.all(restaurants.map((r) => api<MenuItem[]>(`/api/restaurants/${r.id}/menu`)));
    return restaurants.map((r, i) => ({ restaurant: r, items: menus[i] }));
  }, null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  function replace(updated: MenuItem) {
    setData((d) =>
      d?.map((g) => ({ ...g, items: g.items.map((i) => (i.id === updated.id ? updated : i)) })) ?? d,
    );
  }

  async function run(item: MenuItem, fn: () => Promise<MenuItem>) {
    setBusyId(item.id);
    setActionError(null);
    try {
      replace(await fn());
    } catch (e) {
      setActionError(e instanceof ApiError ? `${item.name}: ${e.message}` : "Update failed");
    } finally {
      setBusyId(null);
    }
  }

  const toggle = (item: MenuItem) =>
    run(item, () =>
      api<MenuItem>(`/api/admin/menu-items/${item.id}`, { method: "PATCH", body: { is_available: !item.is_available } }),
    );

  const upload = (item: MenuItem, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return run(item, () => api<MenuItem>(`/api/admin/menu-items/${item.id}/image`, { method: "POST", body: form }));
  };

  if (loading) return <Loading />;
  return (
    <>
      <header className="section-head">
        <div>
          <h1>Menu</h1>
          <p className="muted">Mark dishes sold out, or upload photos (JPEG, PNG or WebP up to 2 MB). Photos are stored in S3.</p>
        </div>
      </header>
      <Alert>{error ?? actionError}</Alert>
      {data?.map(({ restaurant, items }) => (
        <section key={restaurant.id} className="card table-wrap">
          <h2>{restaurant.name}</h2>
          <table className="table">
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className={item.is_available ? "" : "dim"}>
                  <td className="thumb-cell">
                    {item.image_url ? <img className="thumb" src={item.image_url} alt="" /> : <span className="thumb empty-thumb" />}
                  </td>
                  <td><VegMark veg={item.is_veg} /> {item.name}<br /><small className="muted">{item.category}</small></td>
                  <td>{money(item.price)}</td>
                  <td>
                    <label className="btn small ghost file-btn">
                      Upload photo
                      <input
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        disabled={busyId === item.id}
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) upload(item, f);
                          e.target.value = "";
                        }}
                      />
                    </label>
                  </td>
                  <td className="right">
                    <button className={`btn small${item.is_available ? " ghost" : ""}`} disabled={busyId === item.id} onClick={() => toggle(item)}>
                      {item.is_available ? "Mark sold out" : "Make available"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}
