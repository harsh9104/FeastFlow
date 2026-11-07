import { Navigate, Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import { useAuth } from "./context/AuthContext";
import Costs from "./pages/admin/Costs";
import Dashboard from "./pages/admin/Dashboard";
import LoadTests from "./pages/admin/LoadTests";
import Orders from "./pages/admin/Orders";
import Queue from "./pages/admin/Queue";
import Users from "./pages/admin/Users";
import { Login, Register } from "./pages/customer/Auth";
import Menu from "./pages/customer/Menu";
import MyOrders from "./pages/customer/MyOrders";
import Profile from "./pages/customer/Profile";
import { AdminRoute, ProtectedRoute } from "./routes/guards";

function Home() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "ADMIN" ? "/admin/queue" : "/menu"} replace />;
}

export default function App() {
  return (
    <>
      <Navbar />
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute role="CUSTOMER" />}>
            <Route path="/menu" element={<Menu />} />
            <Route path="/orders" element={<MyOrders />} />
            <Route path="/profile" element={<Profile />} />
          </Route>
          <Route element={<AdminRoute />}>
            <Route path="/admin/queue" element={<Queue />} />
            <Route path="/admin/costs" element={<Costs />} />
            <Route path="/admin/dashboard" element={<Dashboard />} />
            <Route path="/admin/orders" element={<Orders />} />
            <Route path="/admin/load-tests" element={<LoadTests />} />
            <Route path="/admin/users" element={<Users />} />
          </Route>
          <Route path="*" element={<Home />} />
        </Routes>
      </main>
    </>
  );
}
