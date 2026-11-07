import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type { Order, OrderDetail, Page } from "../../api/types";
import { PriorityBadge, StatusBadge, money, when } from "../../components/Badges";

function Detail({ id }: { id: number }) {
  const [d, setD] = useState<OrderDetail | null>(null);
  useEffect(() => {
    api<OrderDetail>(`/orders/${id}`).then(setD).catch(() => setD(null));
  }, [id]);
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <div className="detail">
      <ul>
        {d.items.map((i) => (
          <li key={i.menu_item_id}>
            {i.quantity} × {i.name} — {money(i.line_total)}
          </li>
        ))}
      </ul>
      {d.notes && <p className="muted">Notes: {d.notes}</p>}
      <h4>Status timeline</h4>
      <ol className="timeline">
        {d.history.map((h, n) => (
          <li key={n}>
            <StatusBadge status={h.to_status} /> <span className="muted">{when(h.changed_at)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function MyOrders() {
  const [params] = useSearchParams();
  const placed = params.get("placed");
  const [data, setData] = useState<Page<Order> | null>(null);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(placed ? Number(placed) : null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Page<Order>>(`/orders?page=${page}&page_size=10`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [page]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000); // keep statuses fresh
    return () => clearInterval(t);
  }, [load]);

  return (
    <section>
      <h1>My Orders</h1>
      {placed && <p className="success">Order #{placed} placed. We'll keep this page updated.</p>}
      {error && <p className="error">{error}</p>}
      {data && data.items.length === 0 && <p className="muted">No orders yet.</p>}
      {data?.items.map((o) => (
        <article key={o.id} className="card order">
          <div className="row" onClick={() => setOpen(open === o.id ? null : o.id)} role="button" tabIndex={0}>
            <strong>#{o.id}</strong>
            <StatusBadge status={o.status} />
            <PriorityBadge tier={o.tier_at_order} />
            <span className="muted">{when(o.created_at)}</span>
            <strong>{money(o.total_amount)}</strong>
          </div>
          {/* keyed on status so the timeline refetches when the order moves on */}
          {open === o.id && <Detail key={`${o.id}-${o.status}`} id={o.id} />}
        </article>
      ))}
      {data && data.total > data.page_size && (
        <div className="row">
          <button className="btn small" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>Page {page}</span>
          <button className="btn small" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </section>
  );
}
