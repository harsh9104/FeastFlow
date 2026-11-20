import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useCart } from "../cart";
import {
  IconBag,
  IconBike,
  IconCrown,
  IconGrid,
  IconLogout,
  IconMenu,
  IconParty,
  IconPin,
  IconReceipt,
  IconSearch,
  IconUser,
  IconUsers,
} from "./icons";

function Brand({ to, tag }: { to: string; tag?: string }) {
  return (
    <Link to={to} className="brand">
      <span className="brand-mark" aria-hidden>🍲</span>
      <span className="brand-name">FeastFlow</span>
      {tag && <span className="brand-tag">{tag}</span>}
    </Link>
  );
}

export function Layout() {
  const { user } = useAuth();
  return user?.role === "ADMIN" ? <AdminLayout /> : <CustomerLayout />;
}

function CustomerLayout() {
  const { user, logout } = useAuth();
  const cart = useCart();
  const navigate = useNavigate();

  return (
    <div className="shell customer">
      <header className="topbar">
        <div className="topbar-inner">
          <Brand to="/" />
          <span className="location"><IconPin /> <strong>Bengaluru</strong></span>
          <nav className="nav">
            <NavLink to="/" end className="nav-search"><IconSearch /> <span>Search</span></NavLink>
            <NavLink to="/prime" className="nav-prime"><IconCrown /> <span>Prime</span></NavLink>
            {user && <NavLink to="/orders"><IconReceipt /> <span>Orders</span></NavLink>}
            <NavLink to="/cart" className="cart-link">
              <IconBag /> <span>Cart</span>
              {cart.count > 0 && <span className="pill">{cart.count}</span>}
            </NavLink>
            {user ? (
              <button
                className="nav-user"
                title="Log out"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                <IconUser /> <span>{user.name.split(" ")[0]}</span>
                {user.is_prime && <span className="crown" aria-label="Prime member">👑</span>}
              </button>
            ) : (
              <NavLink to="/login"><IconUser /> <span>Sign in</span></NavLink>
            )}
          </nav>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="site-footer">
        <div>
          <Brand to="/" />
          <p className="muted">Hot food from local kitchens. Prime members skip the queue, even on festival nights.</p>
        </div>
        <p className="muted small">Student cloud project on AWS · demo payments only</p>
      </footer>
    </div>
  );
}

function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const links = [
    { to: "/admin", label: "Live orders", icon: <IconGrid />, end: true },
    { to: "/admin/partners", label: "Delivery partners", icon: <IconBike /> },
    { to: "/admin/festival", label: "Festival day", icon: <IconParty /> },
    { to: "/admin/menu", label: "Menu", icon: <IconMenu /> },
    { to: "/admin/users", label: "Customers", icon: <IconUsers /> },
  ];
  return (
    <div className="shell admin">
      <aside className="sidebar">
        <Brand to="/admin" tag="Dispatch" />
        <nav className="side-nav">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end}>
              {l.icon} <span>{l.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div className="side-user">
            <span className="avatar-circle">{user?.name.charAt(0)}</span>
            <div>
              <strong>{user?.name}</strong>
              <small>Restaurant admin</small>
            </div>
          </div>
          <button
            className="side-logout"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            <IconLogout /> <span>Log out</span>
          </button>
        </div>
      </aside>
      <main className="admin-page">
        <Outlet />
      </main>
    </div>
  );
}
