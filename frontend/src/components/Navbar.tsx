import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useCart } from "../context/CartContext";
import { PriorityBadge } from "./Badges";

export default function Navbar() {
  const { user, logout } = useAuth();
  const { count } = useCart();
  const nav = useNavigate();
  if (!user) return null;

  return (
    <header className="navbar">
      <strong className="brand">🍽 FeastFlow</strong>
      <nav>
        {user.role === "CUSTOMER" ? (
          <>
            <NavLink to="/menu">Menu{count > 0 ? ` (${count})` : ""}</NavLink>
            <NavLink to="/orders">My Orders</NavLink>
            <NavLink to="/profile">Profile</NavLink>
          </>
        ) : (
          <>
            <NavLink to="/admin/queue">Queue</NavLink>
            <NavLink to="/admin/dashboard">Dashboard</NavLink>
            <NavLink to="/admin/orders">All Orders</NavLink>
            <NavLink to="/admin/load-tests">Load Tests</NavLink>
            <NavLink to="/admin/costs">Costs</NavLink>
            <NavLink to="/admin/users">Users</NavLink>
          </>
        )}
      </nav>
      <div className="who">
        {user.role === "CUSTOMER" && <PriorityBadge tier={user.subscription_tier} />}
        <span>{user.full_name}</span>
        <button
          className="btn small"
          onClick={() => {
            logout();
            nav("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
