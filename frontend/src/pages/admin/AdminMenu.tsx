import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../../api";
import type { MenuItem } from "../../api";
import { invalidateCatalog, loadCatalog } from "../../catalog";
import { IconEdit, IconPlus, IconSearch } from "../../components/icons";
import { Alert, DishImage, Loading, Modal, VegMark } from "../../components/ui";
import { money } from "../../format";
import { usePolling } from "../../hooks";

interface DishForm {
  restaurant_id: number;
  name: string;
  description: string;
  category: string;
  price: string;
  is_veg: boolean;
  is_bestseller: boolean;
  is_available: boolean;
}

type Editing = { mode: "add"; restaurantId: number } | { mode: "edit"; item: MenuItem };

const IMAGE_TYPES = "image/jpeg,image/png,image/webp";
const MAX_BYTES = 2 * 1024 * 1024;

export function AdminMenu() {
  const { data, error, loading, refresh } = usePolling(() => loadCatalog(true), null);
  const [restaurantId, setRestaurantId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Editing | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const restaurants = useMemo(() => data?.restaurants ?? [], [data]);
  const current = restaurants.find((r) => r.id === restaurantId) ?? restaurants[0];
  const items = useMemo(() => {
    const list = current ? data?.menus[current.id] ?? [] : [];
    const q = query.trim().toLowerCase();
    return q ? list.filter((i) => `${i.name} ${i.category}`.toLowerCase().includes(q)) : list;
  }, [data, current, query]);
  const categories = useMemo(
    () => [...new Set((current ? data?.menus[current.id] ?? [] : []).map((i) => i.category))],
    [data, current],
  );

  async function reload(message?: string) {
    invalidateCatalog();
    await refresh();
    if (message) setNotice(message);
  }

  async function run(item: MenuItem, fn: () => Promise<unknown>, message?: string) {
    setBusyId(item.id);
    setActionError(null);
    setNotice(null);
    try {
      await fn();
      await reload(message);
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
    if (file.size > MAX_BYTES) {
      setActionError(`${item.name}: photo must be under 2 MB`);
      return;
    }
    const form = new FormData();
    form.append("file", file);
    return run(item, () => api<MenuItem>(`/api/admin/menu-items/${item.id}/image`, { method: "POST", body: form }), `Photo updated for ${item.name}`);
  };

  if (loading) return <Loading />;
  const total = restaurants.reduce((n, r) => n + (data?.menus[r.id]?.length ?? 0), 0);

  return (
    <>
      <header className="admin-head">
        <div>
          <h1>Menu</h1>
          <p className="muted">{total} dishes across {restaurants.length} restaurants · photos are stored in S3</p>
        </div>
        {current && (
          <button className="btn primary" onClick={() => setEditing({ mode: "add", restaurantId: current.id })}>
            <IconPlus /> Add dish
          </button>
        )}
      </header>

      <Alert>{error ?? actionError}</Alert>
      <Alert kind="success">{notice}</Alert>

      <div className="tabs">
        {restaurants.map((r) => (
          <button key={r.id} className={`tab${current?.id === r.id ? " active" : ""}`} onClick={() => setRestaurantId(r.id)}>
            {r.name} <span>{data?.menus[r.id]?.length ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="admin-toolbar">
        <label className="menu-search">
          <IconSearch />
          <input placeholder={`Search ${current?.name ?? ""} dishes`} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>

      <div className="admin-dish-grid">
        {current && (
          <button className="admin-dish add-tile" onClick={() => setEditing({ mode: "add", restaurantId: current.id })}>
            <span className="add-circle"><IconPlus /></span>
            <strong>Add a new dish</strong>
            <span className="muted small">to {current.name}</span>
          </button>
        )}
        {items.map((item) => (
          <article key={item.id} className={`admin-dish${item.is_available ? "" : " sold-out"}`}>
            <div className="admin-dish-img">
              <DishImage item={item} />
              {item.is_bestseller && <span className="bestseller on-img">★ Bestseller</span>}
              {!item.is_available && <span className="sold-flag">Sold out</span>}
              <label className="photo-btn" title="Upload a real photo (JPEG, PNG or WebP, under 2 MB)">
                📷 Photo
                <input
                  type="file"
                  accept={IMAGE_TYPES}
                  disabled={busyId === item.id}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) upload(item, f);
                    e.target.value = "";
                  }}
                />
              </label>
            </div>
            <div className="admin-dish-body">
              <div className="admin-dish-title">
                <VegMark veg={item.is_veg} />
                <strong className="one-line">{item.name}</strong>
              </div>
              <span className="muted small">{item.category}</span>
              <div className="admin-dish-foot">
                <span className="price">{money(item.price)}</span>
                <div className="row tight">
                  <button className="icon-btn" title="Edit dish" onClick={() => setEditing({ mode: "edit", item })}>
                    <IconEdit />
                  </button>
                  <button
                    className={`switch-btn${item.is_available ? " on" : ""}`}
                    disabled={busyId === item.id}
                    onClick={() => toggle(item)}
                    title={item.is_available ? "In stock: click to mark sold out" : "Sold out: click to make available"}
                    aria-pressed={item.is_available}
                  >
                    <span className="switch-track"><span className="switch-thumb" /></span>
                  </button>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
      {items.length === 0 && query && <p className="muted">No dishes match “{query}”.</p>}

      {editing && (
        <DishModal
          editing={editing}
          restaurants={restaurants.map((r) => ({ id: r.id, name: r.name }))}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={async (item, verb) => {
            setEditing(null);
            setRestaurantId(item.restaurant_id);
            await reload(`${item.name} ${verb}`);
          }}
        />
      )}
    </>
  );
}

function DishModal({
  editing,
  restaurants,
  categories,
  onClose,
  onSaved,
}: {
  editing: Editing;
  restaurants: { id: number; name: string }[];
  categories: string[];
  onClose: () => void;
  onSaved: (item: MenuItem, verb: string) => void;
}) {
  const isEdit = editing.mode === "edit";
  const [form, setForm] = useState<DishForm>(() =>
    editing.mode === "edit"
      ? {
          restaurant_id: editing.item.restaurant_id,
          name: editing.item.name,
          description: editing.item.description ?? "",
          category: editing.item.category,
          price: String(Number(editing.item.price)),
          is_veg: editing.item.is_veg,
          is_bestseller: editing.item.is_bestseller,
          is_available: editing.item.is_available,
        }
      : {
          restaurant_id: editing.restaurantId,
          name: "",
          description: "",
          category: categories[0] ?? "",
          price: "",
          is_veg: true,
          is_bestseller: false,
          is_available: true,
        },
  );
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(editing.mode === "edit" ? editing.item.image_url : null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof DishForm>(k: K, v: DishForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  function pickPhoto(file: File | undefined) {
    if (!file) return;
    if (!IMAGE_TYPES.split(",").includes(file.type)) return setError("Photo must be JPEG, PNG or WebP");
    if (file.size > MAX_BYTES) return setError("Photo must be under 2 MB");
    setError(null);
    setPhoto(file);
    setPreview(URL.createObjectURL(file));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      category: form.category.trim(),
      price: form.price,
      is_veg: form.is_veg,
      is_bestseller: form.is_bestseller,
      is_available: form.is_available,
    };
    try {
      let item =
        editing.mode === "edit"
          ? await api<MenuItem>(`/api/admin/menu-items/${editing.item.id}`, { method: "PATCH", body })
          : await api<MenuItem>("/api/admin/menu-items", { method: "POST", body: { ...body, restaurant_id: form.restaurant_id } });
      if (photo) {
        const data = new FormData();
        data.append("file", photo);
        try {
          item = await api<MenuItem>(`/api/admin/menu-items/${item.id}/image`, { method: "POST", body: data });
        } catch (err) {
          // The dish is saved; only the photo failed. Say so rather than losing the dish.
          setError(`Dish saved, but the photo upload failed: ${err instanceof ApiError ? err.message : "error"}`);
          setBusy(false);
          return;
        }
      }
      onSaved(item, isEdit ? "updated" : "added to the menu");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the dish");
      setBusy(false);
    }
  }

  return (
    <Modal title={isEdit ? "Edit dish" : "Add a new dish"} onClose={onClose}>
      <form className="form dish-form" onSubmit={submit}>
        <div className="dish-form-grid">
          <label className="photo-drop">
            {preview ? <img src={preview} alt="" /> : (
              <span className="photo-drop-empty">
                <span>📷</span>
                Add a photo
                <small>JPEG, PNG or WebP · max 2 MB</small>
              </span>
            )}
            <input type="file" accept={IMAGE_TYPES} onChange={(e) => pickPhoto(e.target.files?.[0])} />
            {preview && <span className="photo-change">Change photo</span>}
          </label>

          <div className="dish-form-fields">
            <label>
              Restaurant
              <select
                value={form.restaurant_id}
                disabled={isEdit}
                onChange={(e) => set("restaurant_id", Number(e.target.value))}
              >
                {restaurants.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </label>
            <label>
              Dish name
              <input value={form.name} onChange={(e) => set("name", e.target.value)} required minLength={2} maxLength={120} placeholder="e.g. Malai Kofta" autoFocus />
            </label>
            <div className="form-row">
              <label>
                Category
                <input list="dish-categories" value={form.category} onChange={(e) => set("category", e.target.value)} required minLength={2} maxLength={50} placeholder="e.g. Main Course" />
                <datalist id="dish-categories">
                  {categories.map((c) => <option key={c} value={c} />)}
                </datalist>
              </label>
              <label>
                Price (₹)
                <input type="number" inputMode="decimal" min="1" max="99999" step="0.01" value={form.price} onChange={(e) => set("price", e.target.value)} required placeholder="249" />
              </label>
            </div>
          </div>
        </div>

        <label>
          Description <small className="muted">(optional)</small>
          <textarea value={form.description} onChange={(e) => set("description", e.target.value)} maxLength={500} rows={2} placeholder="What makes it tasty? Ingredients, spice level…" />
        </label>

        <div className="choice-row">
          <div className="seg" role="radiogroup" aria-label="Food type">
            <button type="button" className={form.is_veg ? "active veg" : ""} onClick={() => set("is_veg", true)}>
              <VegMark veg /> Veg
            </button>
            <button type="button" className={!form.is_veg ? "active nonveg" : ""} onClick={() => set("is_veg", false)}>
              <VegMark veg={false} /> Non-veg
            </button>
          </div>
          <label className="check">
            <input type="checkbox" checked={form.is_bestseller} onChange={(e) => set("is_bestseller", e.target.checked)} />
            ★ Bestseller
          </label>
          <label className="check">
            <input type="checkbox" checked={form.is_available} onChange={(e) => set("is_available", e.target.checked)} />
            In stock
          </label>
        </div>

        <Alert>{error}</Alert>
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy}>
            {busy ? "Saving…" : isEdit ? "Save changes" : "Add to menu"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
