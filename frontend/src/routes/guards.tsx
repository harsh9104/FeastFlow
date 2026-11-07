import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { Role } from "../api/types";

function Guard({ role }: { role?: Role }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted pad">Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (role && user.role !== role) {
    return <Navigate to={user.role === "ADMIN" ? "/admin/queue" : "/menu"} replace />;
  }
  return <Outlet />;
}

export const ProtectedRoute = ({ role }: { role?: Role }) => <Guard role={role} />;
export const AdminRoute = () => <Guard role="ADMIN" />;
