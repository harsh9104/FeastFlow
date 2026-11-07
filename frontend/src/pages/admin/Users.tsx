import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Page, Tier, User } from "../../api/types";
import { PriorityBadge } from "../../components/Badges";

export default function Users() {
  const [tier, setTierFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<User> | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    const q = new URLSearchParams({ page: String(page), page_size: "20" });
    if (tier) q.set("tier", tier);
    api<Page<User>>(`/admin/users?${q}`).then(setData).catch((e) => setError(e.message));
  }, [tier, page]);

  useEffect(load, [load]);

  async function change(u: User, t: Tier) {
    try {
      await api(`/admin/users/${u.id}/subscription`, { method: "PATCH", body: { subscription_tier: t } });
      setError("");
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section>
      <h1>Users</h1>
      <select value={tier} onChange={(e) => { setTierFilter(e.target.value); setPage(1); }}>
        <option value="">All tiers</option>
        <option>FREE</option>
        <option>PREMIUM</option>
      </select>
      {error && <p className="error">{error}</p>}
      <table className="table">
        <thead>
          <tr><th>ID</th><th>Name</th><th>Email</th><th>Role</th><th>Plan</th><th /></tr>
        </thead>
        <tbody>
          {data?.items.map((u) => (
            <tr key={u.id}>
              <td>{u.id}</td>
              <td>{u.full_name}</td>
              <td>{u.email}</td>
              <td>{u.role}</td>
              <td><PriorityBadge tier={u.subscription_tier} /></td>
              <td>
                {u.role === "CUSTOMER" && (
                  <button className="btn small" onClick={() => change(u, u.subscription_tier === "FREE" ? "PREMIUM" : "FREE")}>
                    Make {u.subscription_tier === "FREE" ? "Premium" : "Free"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data && (
        <div className="row">
          <button className="btn small" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} · {data.total} users</span>
          <button className="btn small" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </section>
  );
}
