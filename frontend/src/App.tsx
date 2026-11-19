import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AdminMenu } from "./pages/admin/AdminMenu";
import { Board } from "./pages/admin/Board";
import { Customers } from "./pages/admin/Customers";
import { Partners } from "./pages/admin/Partners";
import { AuthPage } from "./pages/customer/AuthPage";
import { Cart } from "./pages/customer/Cart";
import { MenuPage } from "./pages/customer/MenuPage";
import { OrderDetail } from "./pages/customer/OrderDetail";
import { Orders } from "./pages/customer/Orders";
import { Prime } from "./pages/customer/Prime";
import { Restaurants } from "./pages/customer/Restaurants";

function RequireUser({ children, role }: { children: ReactNode; role?: "ADMIN" | "CUSTOMER" }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (role && user.role !== role) return <Navigate to={user.role === "ADMIN" ? "/admin" : "/"} replace />;
  return <>{children}</>;
}

/** Admins land on the dispatch board; everyone else browses restaurants. */
function Home() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user?.role === "ADMIN" ? <Navigate to="/admin" replace /> : <Restaurants />;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<AuthPage mode="login" />} />
        <Route path="register" element={<AuthPage mode="register" />} />
        <Route path="restaurants/:id" element={<MenuPage />} />
        <Route path="cart" element={<Cart />} />
        <Route path="prime" element={<Prime />} />
        <Route path="orders" element={<RequireUser role="CUSTOMER"><Orders /></RequireUser>} />
        <Route path="orders/:id" element={<RequireUser role="CUSTOMER"><OrderDetail /></RequireUser>} />

        <Route path="admin" element={<RequireUser role="ADMIN"><Board /></RequireUser>} />
        <Route path="admin/partners" element={<RequireUser role="ADMIN"><Partners /></RequireUser>} />
        <Route path="admin/menu" element={<RequireUser role="ADMIN"><AdminMenu /></RequireUser>} />
        <Route path="admin/users" element={<RequireUser role="ADMIN"><Customers /></RequireUser>} />
        <Route path="*" element={<div className="empty">Page not found.</div>} />
      </Route>
    </Routes>
  );
}
