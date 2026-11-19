import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../../api";
import type { Partner } from "../../api";
import { Alert, Loading } from "../../components/ui";
import { usePolling } from "../../hooks";

export function Partners() {
  const { data, error, loading, refresh } = usePolling(() => api<Partner[]>("/api/admin/partners"), 3000);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      await api<Partner>("/api/admin/partners", { method: "POST", body: { name, phone } });
      setName("");
      setPhone("");
      refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't add partner");
    }
  }

  async function setStatus(p: Partner, status: "AVAILABLE" | "OFFLINE") {
    setBusyId(p.id);
    setRowError(null);
    try {
      await api(`/api/admin/partners/${p.id}`, { method: "PATCH", body: { status } });
      await refresh();
    } catch (err) {
      setRowError(err instanceof ApiError ? `${p.name}: ${err.message}` : "Update failed");
    } finally {
      setBusyId(null);
    }
  }

  if (loading && !data) return <Loading />;
  const partners = data ?? [];
  const count = (s: Partner["status"]) => partners.filter((p) => p.status === s).length;

  return (
    <>
      <header className="section-head">
        <div>
          <h1>Delivery partners</h1>
          <p className="muted">
            Free partners are auto-assigned to ready orders, Prime first. Take partners offline to simulate a rider shortage.
          </p>
        </div>
      </header>
      <section className="stats">
        <div className="card stat"><span className="stat-label">Available</span><span className="stat-value">{count("AVAILABLE")}</span></div>
        <div className="card stat"><span className="stat-label">On delivery</span><span className="stat-value">{count("BUSY")}</span></div>
        <div className="card stat"><span className="stat-label">Offline</span><span className="stat-value">{count("OFFLINE")}</span></div>
      </section>

      <form className="card form inline" onSubmit={add}>
        <h2>Add a partner</h2>
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></label>
        <label>Phone<input value={phone} onChange={(e) => setPhone(e.target.value)} required pattern="\+?[0-9]{8,15}" placeholder="+919876543210" /></label>
        <button className="btn primary">Add</button>
        <Alert>{formError}</Alert>
      </form>

      <Alert>{error ?? rowError}</Alert>
      <section className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Partner</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Current order</th>
              <th>Deliveries</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {partners.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td className="muted">{p.phone}</td>
                <td><span className={`badge partner-${p.status.toLowerCase()}`}>{p.status === "BUSY" ? "On delivery" : p.status === "AVAILABLE" ? "Available" : "Offline"}</span></td>
                <td>{p.current_order_id ? `#${p.current_order_id}` : "–"}</td>
                <td>{p.deliveries_count}</td>
                <td className="right">
                  {p.status === "OFFLINE" ? (
                    <button className="btn small" disabled={busyId === p.id} onClick={() => setStatus(p, "AVAILABLE")}>Start shift</button>
                  ) : (
                    <button className="btn small ghost" disabled={busyId === p.id || p.status === "BUSY"}
                      title={p.status === "BUSY" ? "Can't go offline mid-delivery" : undefined}
                      onClick={() => setStatus(p, "OFFLINE")}>
                      End shift
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
