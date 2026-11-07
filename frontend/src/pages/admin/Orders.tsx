import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Order, Page } from "../../api/types";
import { OrderTable } from "./Queue";

export default function Orders() {
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Order> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) q.set("status", status);
    if (priority) q.set("priority", priority);
    api<Page<Order>>(`/admin/orders?${q}`)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [status, priority, page]);

  return (
    <section>
      <h1>All orders</h1>
      <div className="row">
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Any status</option>
          <option>PENDING</option>
          <option>PREPARING</option>
          <option>COMPLETED</option>
        </select>
        <select value={priority} onChange={(e) => { setPriority(e.target.value); setPage(1); }}>
          <option value="">Any priority</option>
          <option value="1">Premium</option>
          <option value="0">Free</option>
        </select>
      </div>
      {error && <p className="error">{error}</p>}
      <OrderTable orders={data?.items ?? []} empty="No orders match." />
      {data && (
        <div className="row">
          <button className="btn small" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} · {data.total} orders</span>
          <button className="btn small" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </section>
  );
}
