import { useEffect, useState } from "react";
import api from "../api";

// Wetworks (Paint / Tile / Stone / Metal) + furniture (Fabric / Stone / Metal / Accessories).
const PURCHASE_CATEGORIES = ["Paint", "Tile", "Stone", "Metal", "Fabric", "Accessories", "Other"];

export default function AdminSupportItems() {
  const [items, setItems] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [purchasingCompanies, setPurchasingCompanies] = useState([]);
  const [search, setSearch] = useState("");

  const load = () => {
    api.get("/support-items").then((r) => setItems(r.data));
    api.get("/vendors").then((r) => setVendors(r.data));
    api.get("/purchasing-companies").then((r) => setPurchasingCompanies(r.data));
  };
  useEffect(load, []);

  const filtered = items.filter((i) => i.name.toLowerCase().includes(search.toLowerCase()));

  const save = async (item, patch) => {
    const res = await api.put(`/support-items/${item.id}`, {
      name: item.name,
      default_code: item.default_code,
      odoo_id: item.odoo_id,
      uom: item.uom,
      purchase_category: item.purchase_category,
      default_vendor_id: item.default_vendor_id,
      purchasing_company_id: item.purchasing_company_id,
      ...patch,
    });
    setItems((prev) => prev.map((i) => (i.id === item.id ? res.data : i)));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-slate-800">BOM / Support Items</h1>
        <div className="text-xs text-slate-500">
          Purchasing company decides which company's product import list the item goes on when it's used in a BOM.
        </div>
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search support items..."
        className="border rounded-md px-3 py-2 text-sm flex-1 max-w-sm bg-white mb-4"
      />

      <div className="bg-white border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b bg-slate-50">
              <th className="px-4 py-2 font-normal">Support item</th>
              <th className="px-4 py-2 font-normal">UoM</th>
              <th className="px-4 py-2 font-normal">Purchase category</th>
              <th className="px-4 py-2 font-normal">Default vendor</th>
              <th className="px-4 py-2 font-normal">Purchasing company</th>
              <th className="px-4 py-2 font-normal">Odoo id</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.id} className="border-b last:border-0 hover:bg-slate-50">
                <td className="px-4 py-2">{item.name}</td>
                <td className="px-4 py-2 text-slate-500">{item.uom}</td>
                <td className="px-4 py-2">
                  <select
                    value={item.purchase_category || ""}
                    onChange={(e) => save(item, { purchase_category: e.target.value || null })}
                    className="border rounded-md px-2 py-1 text-sm bg-white"
                  >
                    <option value="">--</option>
                    {PURCHASE_CATEGORIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2">
                  <select
                    value={item.default_vendor_id || ""}
                    onChange={(e) => save(item, { default_vendor_id: e.target.value ? Number(e.target.value) : null })}
                    className="w-60 border rounded-md px-2 py-1 text-sm bg-white"
                  >
                    <option value="">--</option>
                    {vendors.map((v) => (
                      <option key={v.id} value={v.id}>{v.name}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2">
                  <select
                    value={item.purchasing_company_id || ""}
                    onChange={(e) => save(item, { purchasing_company_id: e.target.value ? Number(e.target.value) : null })}
                    className="w-60 border rounded-md px-2 py-1 text-sm bg-white"
                  >
                    <option value="">-- (use product's)</option>
                    {purchasingCompanies.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2">
                  <OdooIdCell item={item} onSave={(v) => save(item, { odoo_id: v || null })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OdooIdCell({ item, onSave }) {
  const [value, setValue] = useState(item.odoo_id || "");
  useEffect(() => setValue(item.odoo_id || ""), [item.odoo_id]);
  return (
    <input
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => value !== (item.odoo_id || "") && onSave(value)}
      placeholder="__export__.product_template_..."
      className="w-56 border rounded-md px-2 py-1 text-xs font-mono"
    />
  );
}
