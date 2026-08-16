import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useCurrentUser } from "./RequireAuth";
import { clearToken } from "../auth";

const navItem = ({ isActive }) =>
  `px-3 py-2 text-sm font-medium tracking-wide transition border-b-2 ${
    isActive ? "text-ruby border-ruby" : "text-ink/60 hover:text-ink border-transparent"
  }`;

export default function Layout() {
  const user = useCurrentUser();
  const navigate = useNavigate();

  const logout = () => {
    clearToken();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex flex-col bg-cream text-ink">
      <header className="border-b border-ink/10 bg-cream sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/ifield-logo.png" alt="i-field" className="h-6 w-auto" />
            <div className="border-l border-ink/15 pl-3 hidden sm:block">
              <div className="font-display text-sm font-semibold text-ink leading-tight">Wetworks Estimator</div>
              <div className="text-[11px] uppercase tracking-wider text-ink/40 leading-tight">Turnkey contracting estimation</div>
            </div>
          </div>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navItem}>Projects</NavLink>
            <NavLink to="/admin/products" className={navItem}>Products</NavLink>
            <NavLink to="/admin/countries" className={navItem}>Countries</NavLink>
            {user?.is_admin && <NavLink to="/admin/users" className={navItem}>Users</NavLink>}
            <div className="flex items-center gap-2 pl-3 ml-2 border-l border-ink/15">
              <span className="text-xs text-ink/50">{user?.username}</span>
              <button onClick={logout} className="text-xs text-ink/50 hover:text-ruby">
                Log out
              </button>
            </div>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 relative">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-ink/40 py-4 border-t border-ink/10">
        i&middot;field Wetworks Estimator &middot; self-hosted
      </footer>
    </div>
  );
}
