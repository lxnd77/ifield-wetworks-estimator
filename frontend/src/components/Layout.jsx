import { NavLink, Outlet } from "react-router-dom";

const navItem = ({ isActive }) =>
  `px-3 py-2 rounded-md text-sm font-medium transition ${
    isActive ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"
  }`;

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold text-sm">
              IF
            </div>
            <div>
              <div className="font-semibold text-slate-800 leading-tight">I-Field Wetworks Estimator</div>
              <div className="text-xs text-slate-400 leading-tight">Turnkey contracting estimation</div>
            </div>
          </div>
          <nav className="flex gap-1">
            <NavLink to="/" end className={navItem}>Projects</NavLink>
            <NavLink to="/admin/products" className={navItem}>Products</NavLink>
            <NavLink to="/admin/countries" className={navItem}>Countries</NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-slate-400 py-4">
        I-Field Wetworks Estimator &middot; self-hosted
      </footer>
    </div>
  );
}
