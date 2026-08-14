import { useEffect, useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import api, { money, num } from "../api";

export default function ProjectDetail() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [lines, setLines] = useState([]);
  const [products, setProducts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [newLocationName, setNewLocationName] = useState("");
  const [error, setError] = useState("");

  const load = () => {
    api.get(`/projects/${id}`).then((r) => setProject(r.data));
    api.get(`/projects/${id}/estimate-lines`).then((r) => setLines(r.data));
    api.get(`/projects/${id}/summary`).then((r) => setSummary(r.data));
    api.get("/products").then((r) => setProducts(r.data));
  };
  useEffect(load, [id]);

  const linesByLocation = useMemo(() => {
    const map = {};
    for (const l of lines) {
      (map[l.location_id] ||= []).push(l);
    }
    return map;
  }, [lines]);

  const addLocation = async (e) => {
    e.preventDefault();
    if (!newLocationName.trim()) return;
    await api.post(`/projects/${id}/locations`, { name: newLocationName.trim() });
    setNewLocationName("");
    load();
  };

  const removeLocation = async (locId) => {
    if (!confirm("Remove this location and its estimate lines?")) return;
    await api.delete(`/locations/${locId}`);
    load();
  };

  const removeLine = async (lineId) => {
    await api.delete(`/estimate-lines/${lineId}`);
    load();
  };

  const download = async (kind) => {
    setError("");
    try {
      const res = await api.get(`/projects/${id}/export/${kind}`, { responseType: "blob" });
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : `${kind}.xlsx`;
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError("Export failed. Add at least one estimate line first.");
    }
  };

  if (!project) return <div className="text-slate-400 text-sm">Loading...</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs text-ruby hover:underline">&larr; All projects</Link>
        <div className="flex items-start justify-between mt-1">
          <div>
            <h1 className="text-xl font-semibold text-slate-800">{project.name}</h1>
            <div className="text-xs text-slate-500 mt-1">
              {project.country.name} &middot; {project.start_date} &rarr; {project.end_date} &middot; margin {project.default_margin_pct}%
              {project.country.is_template && (
                <span className="ml-2 text-amber-600 font-medium">country data not yet configured</span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => download("sale-estimation")} className="text-sm px-3 py-2 rounded-md border bg-white hover:bg-slate-50">
              Export Sale Estimation (.xlsx)
            </button>
            <button onClick={() => download("bom")} className="text-sm px-3 py-2 rounded-md border bg-white hover:bg-slate-50">
              Export BOM (.xlsx)
            </button>
          </div>
        </div>
        {error && <div className="text-xs text-red-600 mt-2">{error}</div>}
      </div>

      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <SummaryStat label="Material cost" value={money(summary.material_total)} />
          <SummaryStat label="Labor cost" value={money(summary.labor_total)} />
          <SummaryStat label="Total cost" value={money(summary.cost_total)} highlight />
          <SummaryStat label="Sales value" value={money(summary.sales_total)} highlight />
          <SummaryStat
            label="Needs setup"
            value={summary.needs_setup_count}
            warn={summary.needs_setup_count > 0}
          />
        </div>
      )}

      <div className="space-y-4">
        {project.locations.map((loc) => (
          <LocationBlock
            key={loc.id}
            location={loc}
            lines={linesByLocation[loc.id] || []}
            products={products}
            project={project}
            onRemoveLocation={() => removeLocation(loc.id)}
            onRemoveLine={removeLine}
            onChanged={load}
          />
        ))}

        <form onSubmit={addLocation} className="flex gap-2">
          <input
            value={newLocationName}
            onChange={(e) => setNewLocationName(e.target.value)}
            placeholder="New location name (e.g. Lobby, King Rooms)"
            className="border rounded-md px-3 py-2 text-sm flex-1 max-w-xs bg-white"
          />
          <button className="text-sm px-4 py-2 rounded-md bg-slate-800 text-white hover:bg-slate-900">
            + Add location
          </button>
        </form>
      </div>
    </div>
  );
}

function SummaryStat({ label, value, highlight, warn }) {
  return (
    <div className={`rounded-lg border p-3 bg-white ${highlight ? "border-ruby/40" : ""} ${warn ? "border-amber-300" : ""}`}>
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-lg font-semibold ${warn ? "text-amber-600" : "text-slate-800"}`}>{value}</div>
    </div>
  );
}

function LocationBlock({ location, lines, products, project, onRemoveLocation, onRemoveLine, onChanged }) {
  const [adding, setAdding] = useState(false);
  const total = lines.reduce((s, l) => s + (l.material_cost_per_unit + l.labor_cost_per_unit) * l.qty, 0);

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b">
        <div className="font-medium text-slate-800">{location.name}</div>
        <div className="flex items-center gap-3">
          <div className="text-sm text-slate-500">{money(total)}</div>
          <button onClick={() => setAdding(true)} className="text-xs px-2 py-1 rounded border bg-white hover:bg-slate-100">
            + Line item
          </button>
          <button onClick={onRemoveLocation} className="text-xs text-red-500 hover:underline">
            remove location
          </button>
        </div>
      </div>

      {lines.length === 0 ? (
        <div className="text-xs text-slate-400 px-4 py-4">No line items yet.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b">
              <th className="px-4 py-2 font-normal">Product</th>
              <th className="px-2 py-2 font-normal text-right">Qty</th>
              <th className="px-2 py-2 font-normal text-right">Material/unit</th>
              <th className="px-2 py-2 font-normal text-right">Labor/unit</th>
              <th className="px-2 py-2 font-normal text-right">Total/unit</th>
              <th className="px-2 py-2 font-normal text-right">Line total</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.id} className="border-b last:border-0">
                <td className="px-4 py-2">
                  {l.product.name}
                  {l.product.needs_setup && (
                    <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                      needs setup
                    </span>
                  )}
                </td>
                <td className="px-2 py-2 text-right">{num(l.qty, 1)} {l.product.uom}</td>
                <td className="px-2 py-2 text-right">{money(l.material_cost_per_unit)}</td>
                <td className="px-2 py-2 text-right">{money(l.labor_cost_per_unit)}</td>
                <td className="px-2 py-2 text-right">{money(l.material_cost_per_unit + l.labor_cost_per_unit)}</td>
                <td className="px-2 py-2 text-right font-medium">
                  {money((l.material_cost_per_unit + l.labor_cost_per_unit) * l.qty)}
                </td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => onRemoveLine(l.id)} className="text-xs text-red-500 hover:underline">
                    remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {adding && (
        <AddLineForm
          locationId={location.id}
          projectId={project.id}
          products={products}
          onClose={() => setAdding(false)}
          onAdded={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function AddLineForm({ locationId, projectId, products, onClose, onAdded }) {
  const [productId, setProductId] = useState("");
  const [qty, setQty] = useState("");
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);

  const filtered = products.filter((p) => p.name.toLowerCase().includes(search.toLowerCase()));
  const selected = products.find((p) => p.id === Number(productId));

  const submit = async (e) => {
    e.preventDefault();
    if (!productId || !qty) return;
    setSaving(true);
    try {
      await api.post(`/projects/${projectId}/estimate-lines`, {
        location_id: locationId,
        product_id: Number(productId),
        qty: Number(qty),
      });
      onAdded();
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="p-4 border-t bg-slate-50 flex flex-wrap items-end gap-2">
      <div className="flex-1 min-w-[220px]">
        <label className="text-xs text-slate-500">Product</label>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search product..."
          className="w-full border rounded-md px-2 py-1.5 text-sm mb-1"
        />
        <select required value={productId} onChange={(e) => setProductId(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm">
          <option value="">Select product...</option>
          {filtered.map((p) => (
            <option key={p.id} value={p.id}>
              {p.category} &middot; {p.name} {p.needs_setup ? " (needs setup)" : ""}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="text-xs text-slate-500">Qty {selected ? `(${selected.uom})` : ""}</label>
        <input required type="number" step="0.01" value={qty} onChange={(e) => setQty(e.target.value)} className="w-28 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <button disabled={saving} className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Adding..." : "Add"}
      </button>
      <button type="button" onClick={onClose} className="text-sm px-3 py-1.5 rounded-md border bg-white">
        Cancel
      </button>
      {selected?.needs_setup && (
        <div className="text-xs text-amber-600 w-full">
          This product has no coverage/BOM data yet for the project's country -- cost will show as $0 until an admin configures it.
        </div>
      )}
    </form>
  );
}
