import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../api";

export default function AdminProductDetail() {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [supportItems, setSupportItems] = useState([]);
  const [countries, setCountries] = useState([]);
  const [countryId, setCountryId] = useState("");
  const [prices, setPrices] = useState({});

  const load = () => {
    api.get(`/products/${id}`).then((r) => setProduct(r.data));
    api.get("/support-items").then((r) => setSupportItems(r.data));
    api.get("/countries").then((r) => setCountries(r.data));
  };
  useEffect(load, [id]);

  useEffect(() => {
    if (!countries.length) return;
    if (!countryId) setCountryId(countries[0].id);
  }, [countries]);

  useEffect(() => {
    if (!countryId) return;
    api.get(`/countries/${countryId}/material-prices`).then((r) => {
      const map = {};
      r.data.forEach((row) => (map[row.support_item_id] = row));
      setPrices(map);
    });
  }, [countryId]);

  if (!product) return <div className="text-slate-400 text-sm">Loading...</div>;

  const savePrice = async (supportItemId, value) => {
    const res = await api.put(`/countries/${countryId}/material-prices`, {
      support_item_id: supportItemId,
      unit_price_local: Number(value),
    });
    setPrices((p) => ({ ...p, [supportItemId]: res.data }));
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/admin/products" className="text-xs text-indigo-600 hover:underline">&larr; All products</Link>
        <h1 className="text-xl font-semibold text-slate-800 mt-1">{product.name}</h1>
        <div className="text-xs text-slate-500">{product.category} &middot; {product.uom}</div>
      </div>

      <CoverageRateEditor product={product} onSaved={load} />

      <BomEditor product={product} supportItems={supportItems} onChanged={load} />

      <div className="bg-white border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium text-slate-800">Material prices</h2>
          <select value={countryId} onChange={(e) => setCountryId(e.target.value)} className="border rounded-md px-2 py-1 text-sm">
            {countries.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b">
              <th className="py-1 font-normal">Support item</th>
              <th className="py-1 font-normal text-right">Unit price (USD)</th>
            </tr>
          </thead>
          <tbody>
            {product.bom_lines.map((line) => (
              <PriceRow
                key={line.support_item.id}
                item={line.support_item}
                price={prices[line.support_item.id]?.unit_price_local ?? ""}
                onSave={(v) => savePrice(line.support_item.id, v)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PriceRow({ item, price, onSave }) {
  const [value, setValue] = useState(price);
  useEffect(() => setValue(price), [price]);
  return (
    <tr className="border-b last:border-0">
      <td className="py-1.5">{item.name}</td>
      <td className="py-1.5 text-right">
        <input
          type="number"
          step="0.0001"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => value !== "" && Number(value) !== Number(price) && onSave(value)}
          className="w-28 border rounded px-2 py-1 text-right text-sm"
        />
      </td>
    </tr>
  );
}

function CoverageRateEditor({ product, onSaved }) {
  const cr = product.coverage_rate;
  const [form, setForm] = useState({
    primary_coverage_per_day: cr?.primary_coverage_per_day ?? "",
    secondary_coverage_per_day: cr?.secondary_coverage_per_day ?? 0,
    inhouse_count: cr?.inhouse_count ?? 2,
    local_count: cr?.local_count ?? 0,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm({
      primary_coverage_per_day: cr?.primary_coverage_per_day ?? "",
      secondary_coverage_per_day: cr?.secondary_coverage_per_day ?? 0,
      inhouse_count: cr?.inhouse_count ?? 2,
      local_count: cr?.local_count ?? 0,
    });
  }, [cr]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put(`/products/${product.id}/coverage-rate`, {
        primary_coverage_per_day: Number(form.primary_coverage_per_day),
        secondary_coverage_per_day: Number(form.secondary_coverage_per_day || 0),
        inhouse_count: Number(form.inhouse_count),
        local_count: Number(form.local_count),
      });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="bg-white border rounded-lg p-4">
      <h2 className="font-medium text-slate-800 mb-3">Coverage rate (labor)</h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Field label={`Primary coverage/day (${product.uom})`} value={form.primary_coverage_per_day} onChange={set("primary_coverage_per_day")} required />
        <Field label="Secondary (grouting) coverage/day" value={form.secondary_coverage_per_day} onChange={set("secondary_coverage_per_day")} />
        <Field label="In-house crew count" value={form.inhouse_count} onChange={set("inhouse_count")} />
        <Field label="Local labor count" value={form.local_count} onChange={set("local_count")} />
      </div>
      <button disabled={saving} className="mt-3 text-sm px-4 py-1.5 rounded-md bg-indigo-600 text-white hover:bg-indigo-700">
        {saving ? "Saving..." : "Save coverage rate"}
      </button>
    </form>
  );
}

function Field({ label, value, onChange, required }) {
  return (
    <div>
      <label className="text-xs text-slate-500">{label}</label>
      <input type="number" step="0.01" required={required} value={value} onChange={onChange} className="w-full border rounded-md px-2 py-1.5 text-sm" />
    </div>
  );
}

function BomEditor({ product, supportItems, onChanged }) {
  const [adding, setAdding] = useState(false);
  const [mode, setMode] = useState("existing");
  const [supportItemId, setSupportItemId] = useState("");
  const [newName, setNewName] = useState("");
  const [newUom, setNewUom] = useState(product.uom);
  const [qty, setQty] = useState("1");
  const [wastage, setWastage] = useState("0");
  const [markup, setMarkup] = useState("0");
  const [role, setRole] = useState("fixing");
  const [saving, setSaving] = useState(false);

  const removeLine = async (lineId) => {
    await api.delete(`/bom-lines/${lineId}`);
    onChanged();
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        qty_per_unit: Number(qty),
        wastage_pct: Number(wastage),
        markup_pct: Number(markup),
        role,
        sort_order: product.bom_lines.length,
      };
      if (mode === "existing") payload.support_item_id = Number(supportItemId);
      else {
        payload.new_support_item_name = newName;
        payload.new_support_item_uom = newUom;
      }
      await api.post(`/products/${product.id}/bom-lines`, payload);
      setAdding(false);
      setQty("1");
      setWastage("0");
      setMarkup("0");
      setNewName("");
      onChanged();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-medium text-slate-800">BOM / recipe (support items)</h2>
        <button onClick={() => setAdding(true)} className="text-xs px-2 py-1 rounded border hover:bg-slate-50">
          + Add line
        </button>
      </div>

      {product.bom_lines.length === 0 ? (
        <div className="text-xs text-slate-400">No BOM lines yet.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b">
              <th className="py-1 font-normal">Support item</th>
              <th className="py-1 font-normal text-right">Qty/unit</th>
              <th className="py-1 font-normal text-right">Wastage %</th>
              <th className="py-1 pr-3 font-normal text-right">Markup %</th>
              <th className="py-1 pl-3 font-normal">Role</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {product.bom_lines.map((l) => (
              <tr key={l.id} className="border-b last:border-0">
                <td className="py-1.5">{l.support_item.name}</td>
                <td className="py-1.5 text-right">{l.qty_per_unit}</td>
                <td className="py-1.5 text-right">{(l.wastage_pct * 100).toFixed(1)}</td>
                <td className="py-1.5 pr-3 text-right">{(l.markup_pct * 100).toFixed(1)}</td>
                <td className="py-1.5 pl-3">{l.role}</td>
                <td className="py-1.5 text-right">
                  <button onClick={() => removeLine(l.id)} className="text-xs text-red-500 hover:underline">remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {adding && (
        <form onSubmit={submit} className="mt-4 pt-4 border-t space-y-2">
          <div className="flex gap-3 text-xs">
            <label className="flex items-center gap-1">
              <input type="radio" checked={mode === "existing"} onChange={() => setMode("existing")} /> Existing support item
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={mode === "new"} onChange={() => setMode("new")} /> New support item
            </label>
          </div>
          {mode === "existing" ? (
            <select required value={supportItemId} onChange={(e) => setSupportItemId(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm">
              <option value="">Select...</option>
              {supportItems.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          ) : (
            <div className="flex gap-2">
              <input required placeholder="Name" value={newName} onChange={(e) => setNewName(e.target.value)} className="flex-1 border rounded-md px-2 py-1.5 text-sm" />
              <input placeholder="UoM" value={newUom} onChange={(e) => setNewUom(e.target.value)} className="w-24 border rounded-md px-2 py-1.5 text-sm" />
            </div>
          )}
          <div className="grid grid-cols-4 gap-2">
            <Field label="Qty/unit" value={qty} onChange={(e) => setQty(e.target.value)} required />
            <Field label="Wastage % (0.1 = 10%)" value={wastage} onChange={(e) => setWastage(e.target.value)} />
            <Field label="Markup % (0.1 = 10%)" value={markup} onChange={(e) => setMarkup(e.target.value)} />
            <div>
              <label className="text-xs text-slate-500">Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm">
                <option value="primary">primary</option>
                <option value="fixing">fixing</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button disabled={saving} className="text-sm px-4 py-1.5 rounded-md bg-indigo-600 text-white hover:bg-indigo-700">
              {saving ? "Saving..." : "Add BOM line"}
            </button>
            <button type="button" onClick={() => setAdding(false)} className="text-sm px-3 py-1.5 rounded-md border">Cancel</button>
          </div>
        </form>
      )}
    </div>
  );
}
