import { useEffect, useState, useMemo, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import api, { money, num } from "../api";

let tempIdCounter = 0;
const newTempId = () => `new-${++tempIdCounter}-${Date.now()}`;
const isTemp = (id) => typeof id === "string";

// Mirrors service.py::line_totals() exactly, computed client-side from the
// cached per-unit cost map so editing (qty/margin/product/add/remove) never
// needs an API round trip -- only Save and Export do.
function lineCosts(line, costMap, project) {
  const c = costMap[line.product_id] || { material_cost_per_unit: 0, labor_cost_per_unit: 0, needs_setup: true };
  const materialTotal = c.material_cost_per_unit * line.qty;
  const laborTotal = c.labor_cost_per_unit * line.qty;
  const costTotal = materialTotal + laborTotal;
  const margin = line.margin_pct_override ?? project.default_margin_pct ?? 0;
  const salesValue = costTotal * (1 + margin / 100);
  return {
    materialPerUnit: c.material_cost_per_unit,
    laborPerUnit: c.labor_cost_per_unit,
    materialTotal,
    laborTotal,
    costTotal,
    salesValue,
    needsSetup: c.needs_setup,
  };
}

const lineFields = (l) => ({
  location_id: l.location_id,
  product_id: l.product_id,
  qty: l.qty,
  margin_pct_override: l.margin_pct_override ?? null,
  drawing_no: l.drawing_no || "",
  remark: l.remark || "",
});
const locFields = (l) => ({ name: l.name });

export default function ProjectDetail() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [products, setProducts] = useState([]);
  const [costMap, setCostMap] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [savedLocations, setSavedLocations] = useState([]);
  const [savedLines, setSavedLines] = useState([]);
  const [draftLocations, setDraftLocations] = useState([]);
  const [draftLines, setDraftLines] = useState([]);

  const load = useCallback(() => {
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/projects/${id}/estimate-lines`),
      api.get(`/projects/${id}/product-costs`),
      api.get("/products"),
    ]).then(([projectRes, linesRes, costsRes, productsRes]) => {
      setProject(projectRes.data);
      setProducts(productsRes.data);
      setCostMap(costsRes.data);
      const locs = projectRes.data.locations;
      const lines = linesRes.data.map((l) => ({
        id: l.id, location_id: l.location_id, product_id: l.product_id, qty: l.qty,
        margin_pct_override: l.margin_pct_override, drawing_no: l.drawing_no, remark: l.remark,
      }));
      setSavedLocations(locs);
      setSavedLines(lines);
      setDraftLocations(locs);
      setDraftLines(lines);
    });
  }, [id]);
  useEffect(load, [load]);

  const dirty = useMemo(() => {
    if (draftLocations.length !== savedLocations.length || draftLines.length !== savedLines.length) return true;
    const locsChanged = draftLocations.some((l) => {
      if (isTemp(l.id)) return true;
      const prev = savedLocations.find((s) => s.id === l.id);
      return !prev || JSON.stringify(locFields(prev)) !== JSON.stringify(locFields(l));
    });
    if (locsChanged) return true;
    return draftLines.some((l) => {
      if (isTemp(l.id) || isTemp(l.location_id)) return true;
      const prev = savedLines.find((s) => s.id === l.id);
      return !prev || JSON.stringify(lineFields(prev)) !== JSON.stringify(lineFields(l));
    });
  }, [draftLocations, savedLocations, draftLines, savedLines]);

  const linesByLocation = useMemo(() => {
    const map = {};
    for (const l of draftLines) (map[l.location_id] ||= []).push(l);
    return map;
  }, [draftLines]);

  const summary = useMemo(() => {
    if (!project) return null;
    let material = 0, labor = 0, sales = 0, needsSetup = 0;
    for (const l of draftLines) {
      const c = lineCosts(l, costMap, project);
      material += c.materialTotal;
      labor += c.laborTotal;
      sales += c.salesValue;
      if (c.needsSetup) needsSetup += 1;
    }
    return { material_total: material, labor_total: labor, cost_total: material + labor, sales_total: sales, needs_setup_count: needsSetup };
  }, [draftLines, costMap, project]);

  const addLocation = (name) => {
    setDraftLocations((prev) => [...prev, { id: newTempId(), name, sort_order: prev.length }]);
  };

  const removeLocation = (locId) => {
    if (!confirm("Remove this location and its estimate lines?")) return;
    setDraftLocations((prev) => prev.filter((l) => l.id !== locId));
    setDraftLines((prev) => prev.filter((l) => l.location_id !== locId));
  };

  const addLine = (locationId, line) => {
    setDraftLines((prev) => [...prev, { id: newTempId(), location_id: locationId, ...line }]);
  };

  const updateLine = (lineId, patch) => {
    setDraftLines((prev) => prev.map((l) => (l.id === lineId ? { ...l, ...patch } : l)));
  };

  const removeLine = (lineId) => {
    setDraftLines((prev) => prev.filter((l) => l.id !== lineId));
  };

  const doSave = async () => {
    setSaving(true);
    setError("");
    try {
      const idMap = {};
      for (const loc of draftLocations) {
        if (isTemp(loc.id)) {
          const res = await api.post(`/projects/${id}/locations`, { name: loc.name });
          idMap[loc.id] = res.data.id;
        }
      }
      const draftLocIds = new Set(draftLocations.filter((l) => !isTemp(l.id)).map((l) => l.id));
      for (const loc of savedLocations) {
        if (!draftLocIds.has(loc.id)) await api.delete(`/locations/${loc.id}`);
      }
      const removedLocationIds = new Set(savedLocations.filter((l) => !draftLocIds.has(l.id)).map((l) => l.id));
      const draftLineIds = new Set(draftLines.filter((l) => !isTemp(l.id)).map((l) => l.id));
      for (const line of savedLines) {
        if (!draftLineIds.has(line.id) && !removedLocationIds.has(line.location_id)) {
          await api.delete(`/estimate-lines/${line.id}`);
        }
      }
      for (const line of draftLines) {
        const resolvedLocationId = isTemp(line.location_id) ? idMap[line.location_id] : line.location_id;
        const payload = { ...lineFields(line), location_id: resolvedLocationId };
        if (isTemp(line.id)) {
          await api.post(`/projects/${id}/estimate-lines`, payload);
        } else {
          const prev = savedLines.find((s) => s.id === line.id);
          if (!prev || JSON.stringify(lineFields(prev)) !== JSON.stringify(lineFields(line))) {
            await api.put(`/estimate-lines/${line.id}`, payload);
          }
        }
      }
      load();
    } finally {
      setSaving(false);
    }
  };

  const download = async (kind) => {
    setError("");
    try {
      if (dirty) await doSave();
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

  if (!project) return <div className="text-ink/40 text-sm">Loading...</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs text-ruby hover:underline">&larr; All projects</Link>
        <div className="flex items-start justify-between mt-1">
          <div>
            <h1 className="text-xl font-semibold text-ink">{project.name}</h1>
            <div className="text-xs text-ink/60 mt-1">
              {project.country.name} &middot; {project.start_date} &rarr; {project.end_date} &middot; margin {project.default_margin_pct}%
              {project.country.is_template && (
                <span className="ml-2 text-amber-600 font-medium">country data not yet configured</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <button onClick={doSave} disabled={saving} className="text-sm px-3 py-2 rounded-md bg-ruby text-white hover:bg-ruby-dark">
                {saving ? "Saving..." : "Save changes"}
              </button>
            )}
            <button onClick={() => download("sale-estimation")} className="text-sm px-3 py-2 rounded-md border bg-white hover:bg-slate-50">
              Export Sale Estimation (.xlsx)
            </button>
            <button onClick={() => download("bom")} className="text-sm px-3 py-2 rounded-md border bg-white hover:bg-slate-50">
              Export BOM (.xlsx)
            </button>
          </div>
        </div>
        {dirty && !saving && (
          <div className="text-xs text-amber-600 mt-2">Unsaved changes -- click Save to persist them.</div>
        )}
        {error && <div className="text-xs text-red-600 mt-2">{error}</div>}
      </div>

      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <SummaryStat label="Material cost" value={money(summary.material_total)} />
          <SummaryStat label="Labor cost" value={money(summary.labor_total)} />
          <SummaryStat label="Total cost" value={money(summary.cost_total)} highlight />
          <SummaryStat label="Sales value" value={money(summary.sales_total)} highlight />
          <SummaryStat label="Needs setup" value={summary.needs_setup_count} warn={summary.needs_setup_count > 0} />
        </div>
      )}

      <div className="space-y-4">
        {draftLocations.map((loc) => (
          <LocationBlock
            key={loc.id}
            location={loc}
            lines={linesByLocation[loc.id] || []}
            products={products}
            costMap={costMap}
            project={project}
            onRemoveLocation={() => removeLocation(loc.id)}
            onAddLine={(line) => addLine(loc.id, line)}
            onUpdateLine={updateLine}
            onRemoveLine={removeLine}
          />
        ))}

        <AddLocationForm onAdd={addLocation} />
      </div>
    </div>
  );
}

function AddLocationForm({ onAdd }) {
  const [name, setName] = useState("");
  const submit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    onAdd(name.trim());
    setName("");
  };
  return (
    <form onSubmit={submit} className="flex gap-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="New location name (e.g. Lobby, King Rooms)"
        className="border rounded-md px-3 py-2 text-sm flex-1 max-w-xs bg-white"
      />
      <button className="text-sm px-4 py-2 rounded-md bg-slate-800 text-white hover:bg-slate-900">
        + Add location
      </button>
    </form>
  );
}

function SummaryStat({ label, value, highlight, warn }) {
  return (
    <div className={`rounded-lg border p-3 bg-white ${highlight ? "border-ruby/40" : ""} ${warn ? "border-amber-300" : ""}`}>
      <div className="text-xs text-ink/40">{label}</div>
      <div className={`text-lg font-semibold ${warn ? "text-amber-600" : "text-ink"}`}>{value}</div>
    </div>
  );
}

function LocationBlock({ location, lines, products, costMap, project, onRemoveLocation, onAddLine, onUpdateLine, onRemoveLine }) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const total = lines.reduce((s, l) => s + lineCosts(l, costMap, project).costTotal, 0);
  const productById = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p])), [products]);

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b">
        <div className="font-medium text-ink">{location.name}</div>
        <div className="flex items-center gap-3">
          <div className="text-sm text-ink/60">{money(total)}</div>
          <button onClick={() => setAdding(true)} className="text-xs px-2 py-1 rounded border bg-white hover:bg-slate-100">
            + Line item
          </button>
          <button onClick={onRemoveLocation} className="text-xs text-red-500 hover:underline">
            remove location
          </button>
        </div>
      </div>

      {lines.length === 0 ? (
        <div className="text-xs text-ink/40 px-4 py-4">No line items yet.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink/40 border-b">
              <th className="px-4 py-2 font-normal">Product</th>
              <th className="px-2 py-2 font-normal text-right">Qty</th>
              <th className="px-2 py-2 font-normal text-right">Material/unit</th>
              <th className="px-2 py-2 font-normal text-right">Labor/unit</th>
              <th className="px-2 py-2 font-normal text-right">Margin</th>
              <th className="px-2 py-2 font-normal text-right">Line total</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => {
              const product = productById[l.product_id];
              const c = lineCosts(l, costMap, project);
              return editingId === l.id ? (
                <tr key={l.id} className="border-b last:border-0">
                  <td colSpan={7}>
                    <LineItemForm
                      products={products}
                      initial={l}
                      onCancel={() => setEditingId(null)}
                      onSubmit={(vals) => {
                        onUpdateLine(l.id, vals);
                        setEditingId(null);
                      }}
                    />
                  </td>
                </tr>
              ) : (
                <tr key={l.id} className="border-b last:border-0 hover:bg-slate-50 cursor-pointer" onClick={() => setEditingId(l.id)}>
                  <td className="px-4 py-2">
                    {product?.name || `#${l.product_id}`}
                    {c.needsSetup && (
                      <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                        needs setup
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right">{num(l.qty, 1)} {product?.uom}</td>
                  <td className="px-2 py-2 text-right">{money(c.materialPerUnit)}</td>
                  <td className="px-2 py-2 text-right">{money(c.laborPerUnit)}</td>
                  <td className="px-2 py-2 text-right">{l.margin_pct_override != null ? `${l.margin_pct_override}%` : "default"}</td>
                  <td className="px-2 py-2 text-right font-medium">{money(c.costTotal)}</td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); onRemoveLine(l.id); }}
                      className="text-xs text-red-500 hover:underline"
                    >
                      remove
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {adding && (
        <div className="p-4 border-t bg-slate-50">
          <LineItemForm
            products={products}
            onCancel={() => setAdding(false)}
            onSubmit={(vals) => {
              onAddLine(vals);
              setAdding(false);
            }}
          />
        </div>
      )}
    </div>
  );
}

function LineItemForm({ products, initial, onCancel, onSubmit }) {
  const [productId, setProductId] = useState(initial?.product_id ?? "");
  const [qty, setQty] = useState(initial?.qty ?? "");
  const [margin, setMargin] = useState(initial?.margin_pct_override ?? "");
  const [drawingNo, setDrawingNo] = useState(initial?.drawing_no ?? "");
  const [remark, setRemark] = useState(initial?.remark ?? "");
  const [search, setSearch] = useState("");

  const filtered = products.filter((p) => p.name.toLowerCase().includes(search.toLowerCase()));
  const selected = products.find((p) => p.id === Number(productId));

  const submit = (e) => {
    e.preventDefault();
    if (!productId || !qty) return;
    onSubmit({
      product_id: Number(productId),
      qty: Number(qty),
      margin_pct_override: margin === "" ? null : Number(margin),
      drawing_no: drawingNo || null,
      remark: remark || null,
    });
  };

  return (
    <form onSubmit={submit} className="p-3 flex flex-wrap items-end gap-2">
      <div className="flex-1 min-w-[220px]">
        <label className="text-xs text-ink/60">Product</label>
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
        <label className="text-xs text-ink/60">Qty {selected ? `(${selected.uom})` : ""}</label>
        <input required type="number" step="0.01" value={qty} onChange={(e) => setQty(e.target.value)} className="w-24 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div>
        <label className="text-xs text-ink/60">Margin % override</label>
        <input type="number" step="0.1" placeholder="default" value={margin} onChange={(e) => setMargin(e.target.value)} className="w-24 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div>
        <label className="text-xs text-ink/60">Drawing #</label>
        <input value={drawingNo} onChange={(e) => setDrawingNo(e.target.value)} className="w-24 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div className="flex-1 min-w-[140px]">
        <label className="text-xs text-ink/60">Remark</label>
        <input value={remark} onChange={(e) => setRemark(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <button className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {initial ? "Save line" : "Add"}
      </button>
      <button type="button" onClick={onCancel} className="text-sm px-3 py-1.5 rounded-md border bg-white">
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
