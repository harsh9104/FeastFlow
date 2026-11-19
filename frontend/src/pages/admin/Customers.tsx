import { useState } from "react";
import { api, parseUtc } from "../../api";
import type { Page, User } from "../../api";
import { Alert, Loading, PrimeBadge } from "../../components/ui";
import { dateTime } from "../../format";
import { usePolling } from "../../hooks";

const PAGE_SIZE = 50;

export function Customers() {
  const [primeOnly, setPrimeOnly] = useState(false);
  const [page, setPage] = useState(1);
  const { data, error, loading } = usePolling(
    () => api<Page<User>>(`/api/admin/users?prime_only=${primeOnly}&page=${page}&page_size=${PAGE_SIZE}`),
    null,
    [primeOnly, page],
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <header className="section-head">
        <div>
          <h1>Customers</h1>
          <p className="muted">{data ? `${data.total} ${primeOnly ? "Prime members" : "accounts"}` : ""}</p>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={primeOnly} onChange={(e) => { setPrimeOnly(e.target.checked); setPage(1); }} />
          Prime members only
        </label>
      </header>
      <Alert>{error}</Alert>
      {loading && !data ? (
        <Loading />
      ) : (
        <section className="card table-wrap">
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Email</th><th>Role</th><th>Prime</th><th>Joined</th></tr>
            </thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td className="muted">{u.email}</td>
                  <td>{u.role === "ADMIN" ? "Admin" : "Customer"}</td>
                  <td>
                    {u.is_prime ? (
                      <><PrimeBadge small /> <small className="muted">until {parseUtc(u.prime_expires_at!).toLocaleDateString()}</small></>
                    ) : "–"}
                  </td>
                  <td className="muted">{u.created_at ? dateTime(u.created_at) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pages > 1 && (
            <div className="pager">
              <button className="btn small ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
              <span className="muted">Page {page} of {pages}</span>
              <button className="btn small ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next →</button>
            </div>
          )}
        </section>
      )}
    </>
  );
}
