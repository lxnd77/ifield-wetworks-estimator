import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";

export default function AdminProducts() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");

  useEffect(() => {
    api.get("/products").then((r) => setProducts(r.data));
  }, []);

  const categories = [...new Set(products.map((p) => p.category))];
  const filtered = products.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) &&
      (!category || p.category === category)
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-slate-800">Wetworks Product Master</h1>
        <div className="text-xs text-slate-500">
          {products.filter((p) => !p.needs_setup).length} / {products.length} configured
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search products..."
          className="border rounded-md px-3 py-2 text-sm flex-1 max-w-sm bg-white"
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="border rounded-md px-3 py-2 text-sm bg-white">
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="bg-white border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b bg-slate-50">
              <th className="px-4 py-2 font-normal">Product</th>
              <th className="px-4 py-2 font-normal">Category</th>
              <th className="px-4 py-2 font-normal">UoM</th>
              <th className="px-4 py-2 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.id} className="border-b last:border-0 hover:bg-slate-50">
                <td className="px-4 py-2">
                  <Link to={`/admin/products/${p.id}`} className="text-ruby hover:underline">
                    {p.name}
                  </Link>
                </td>
                <td className="px-4 py-2 text-slate-500">{p.category}</td>
                <td className="px-4 py-2 text-slate-500">{p.uom}</td>
                <td className="px-4 py-2">
                  {p.needs_setup ? (
                    <span className="text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                      needs setup
                    </span>
                  ) : (
                    <span className="text-[10px] uppercase tracking-wide text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">
                      configured
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
