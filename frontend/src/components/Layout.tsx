import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useCart } from "../cart";
import { PrimeBadge } from "./ui";

export function Layout() {
  const { user, logout } = useAuth();
  const cart = useCart();
  const navigate = useNavigate();
  const isAdmin = user?.role === "ADMIN";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to={isAdmin ? "/admin" : "/"} className="brand">
            <span aria-hidden>🍲</span> FeastFlow
            {isAdmin && <span className="brand-tag">Dispatch</span>}
          </Link>
          <nav className="nav">
            {isAdmin ? (
              <>
                <NavLink to="/admin" end>Orders</NavLink>
                <NavLink to="/admin/partners">Partners</NavLink>
                <NavLink to="/admin/menu">Menu</NavLink>
                <NavLink to="/admin/users">Customers</NavLink>
              </>
            ) : (
              <>
                <NavLink to="/" end>Restaurants</NavLink>
                {user && <NavLink to="/orders">My orders</NavLink>}
                <NavLink to="/prime">Prime</NavLink>
                <NavLink to="/cart" className="cart-link">
                  Cart{cart.count > 0 && <span className="pill">{cart.count}</span>}
                </NavLink>
              </>
            )}
          </nav>
          <div className="account">
            {user ? (
              <>
                <span className="who">
                  {user.name}
                  {user.is_prime && <PrimeBadge small />}
                </span>
                <button
                  className="btn ghost small"
                  onClick={() => {
                    logout();
                    navigate("/login");
                  }}
                >
                  Log out
                </button>
              </>
            ) : (
              <Link to="/login" className="btn small">Log in</Link>
            )}
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
