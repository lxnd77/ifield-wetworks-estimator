import { useEffect, useState, useMemo, useCallback, Fragment } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import api, { money, num } from "../api";
import { laborApplies, bomPerLine, typeLabel, FURNITURE_BOM_CATEGORIES } from "../projectTypes";
import { useCurrentUser } from "../components/RequireAuth";

let tempIdCounter = 0;
const newTempId = () => `new-${++tempIdCounter}-${Date.now()}`;
const isTemp = (id) => typeof id === "string";

// Mirrors service.py::line_totals(). For wetworks the per-unit cost comes
// from the cached per-product cost map, so qty/margin edits never need an
// API round trip. For furniture the per-unit cost is per-line (components +
// Factory Work + OHP, all CNY-converted server-side) -- we show the last
// server-computed value; component and Factory-Work edits go through the API
// / a Save and reload.
function lineCosts(line, costMap, project, lineDataById = {}) {
  const margin = line.margin_pct_override ?? project.default_margin_pct ?? 0;
  const withMargin = (cost) => cost * (1 + margin / 100);

  if (bomPerLine(project.project_type)) {
    const server = lineDataById[line.id] || { material_cost_per_unit: 0 };
    const materialPerUnit = server.material_cost_per_unit || 0;
    const materialTotal = materialPerUnit * line.qty;
    return {
      materialPerUnit, laborPerUnit: 0,
      materialTotal, laborTotal: 0,
      costTotal: materialTotal, salesValue: withMargin(materialTotal),
      needsSetup: false,
    };
  }

  const c = costMap[line.product_id] || { material_cost_per_unit: 0, labor_cost_per_unit: 0, needs_setup: true };
  const materialTotal = c.material_cost_per_unit * line.qty;
  const laborTotal = c.labor_cost_per_unit * line.qty;
  const costTotal = materialTotal + laborTotal;
  return {
    materialPerUnit: c.material_cost_per_unit,
    laborPerUnit: c.labor_cost_per_unit,
    materialTotal,
    laborTotal,
    costTotal,
    salesValue: withMargin(costTotal),
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
  description: l.description || "",
  dimension: l.dimension || "",
  item_code: l.item_code || "",
  factory_work_cost_cny: l.factory_work_cost_cny ?? null,
});
const locFields = (l) => ({ name: l.name });

// The Odoo reference an item exports under: project code + item code, or
// just the project code when the item code is blank (mirrors
// export_excel.reference_code).
const referenceCode = (projectCode, itemCode) =>
  [projectCode, itemCode].map((s) => (s || "").trim()).filter(Boolean).join(" ");

// FastAPI errors: a string detail for our own 4xx, a list for schema errors.
export function errorText(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  if (!err?.response) return `${fallback} (network error -- check your connection and try again)`;
  return fallback;
}

const toDraftLine = (l) => ({
  id: l.id, location_id: l.location_id, product_id: l.product_id, qty: l.qty,
  margin_pct_override: l.margin_pct_override, drawing_no: l.drawing_no, remark: l.remark,
  description: l.description, dimension: l.dimension, item_code: l.item_code,
  factory_work_cost_cny: l.factory_work_cost_cny,
});

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const currentUser = useCurrentUser();
  const [project, setProject] = useState(null);
  const [products, setProducts] = useState([]);
  const [costMap, setCostMap] = useState({});
  const [sellingCompanies, setSellingCompanies] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [supportItems, setSupportItems] = useState([]);
  const [savedLocations, setSavedLocations] = useState([]);
  const [savedLines, setSavedLines] = useState([]);
  const [draftLocations, setDraftLocations] = useState([]);
  const [draftLines, setDraftLines] = useState([]);
  const [componentsByLineId, setComponentsByLineId] = useState({});
  const [lineDataById, setLineDataById] = useState({});

  // Server-computed line data (costs, components). Doesn't touch the
  // location/line drafts, so unsaved edits survive a component change.
  const applyLineData = (data) => {
    setProject(data.project);
    setCostMap(data.product_costs);
    setComponentsByLineId(Object.fromEntries(data.lines.map((l) => [l.id, l.components])));
    setLineDataById(Object.fromEntries(data.lines.map((l) => [l.id, l])));
  };

  // A full workspace (initial load / after Save): also resets the drafts to
  // what the server now holds.
  const applyWorkspace = (data) => {
    applyLineData(data);
    if (data.products) setProducts(data.products);
    if (data.selling_companies) setSellingCompanies(data.selling_companies);
    if (data.support_items) setSupportItems(data.support_items);
    const locs = data.project.locations;
    const lines = data.lines.map(toDraftLine);
    setSavedLocations(locs);
    setSavedLines(lines);
    setDraftLocations(locs);
    setDraftLines(lines);
  };

  // One request for everything the screen needs (was six).
  const load = useCallback(() => {
    setError("");
    api.get(`/projects/${id}/workspace`)
      .then((res) => applyWorkspace(res.data))
      .catch((err) => setError(errorText(err, "Could not load the project.")));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const refreshLineData = async () => {
    const res = await api.get(`/projects/${id}/workspace`, { params: { catalog: false } });
    applyLineData(res.data);
  };

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

  // A line item can only be a product of the project's own type.
  const visibleProducts = useMemo(
    () => (project ? products.filter((p) => p.product_type === project.project_type) : products),
    [products, project]
  );
  const showLabor = project ? laborApplies(project.project_type) : true;

  const summary = useMemo(() => {
    if (!project) return null;
    let material = 0, labor = 0, sales = 0, needsSetup = 0;
    for (const l of draftLines) {
      const c = lineCosts(l, costMap, project, lineDataById);
      material += c.materialTotal;
      labor += c.laborTotal;
      sales += c.salesValue;
      if (c.needsSetup) needsSetup += 1;
    }
    return { material_total: material, labor_total: labor, cost_total: material + labor, sales_total: sales, needs_setup_count: needsSetup };
  }, [draftLines, costMap, project, lineDataById]);

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

  // Sends the whole draft in one request; the server applies it in a single
  // transaction (all or nothing) and returns the saved workspace. Returns
  // true on success.
  const doSave = async () => {
    setSaving(true);
    setError("");
    try {
      const payload = {
        locations: draftLocations.map((l, i) => (
          isTemp(l.id)
            ? { key: l.id, name: l.name, sort_order: l.sort_order ?? i }
            : { id: l.id, name: l.name, sort_order: l.sort_order ?? i }
        )),
        lines: draftLines.map((l) => ({
          ...lineFields(l),
          id: isTemp(l.id) ? null : l.id,
          location_id: isTemp(l.location_id) ? null : l.location_id,
          location_key: isTemp(l.location_id) ? l.location_id : null,
        })),
      };
      const res = await api.put(`/projects/${id}/estimate`, payload);
      applyWorkspace(res.data);
      return true;
    } catch (err) {
      setError(errorText(err, "Could not save your changes -- nothing was saved."));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveComponentCode = async (lineId, componentId, itemCode) => {
    const res = await api.put(`/estimate-line-components/${componentId}/code`, { item_code: itemCode || null });
    setComponentsByLineId((prev) => ({
      ...prev,
      [lineId]: (prev[lineId] || []).map((c) => (c.id === componentId ? res.data : c)),
    }));
  };

  // Furniture component edits hit the API immediately (they're not part of
  // the line draft) and then refresh the server-computed line data --
  // without resetting any unsaved line edits.
  const componentCall = async (fn) => {
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(errorText(err, "Could not save the component."));
    }
    try {
      await refreshLineData();
    } catch (err) {
      setError(errorText(err, "Could not refresh the estimate."));
    }
  };
  const addComponent = (lineId, payload) =>
    componentCall(() => api.post(`/estimate-lines/${lineId}/components`, payload));
  const updateComponent = (componentId, payload) =>
    componentCall(() => api.put(`/estimate-line-components/${componentId}`, payload));
  const deleteComponent = (componentId) =>
    componentCall(() => api.delete(`/estimate-line-components/${componentId}`));

  const saveProjectMeta = async (patch) => {
    const payload = {
      name: project.name, code: project.code, country_id: project.country_id,
      selling_company_id: project.selling_company_id, client_name: project.client_name,
      address: project.address, estimator_name: project.estimator_name,
      start_date: project.start_date, end_date: project.end_date, project_type: project.project_type,
      default_margin_pct: project.default_margin_pct, display_currency: project.display_currency,
      cny_per_usd: project.cny_per_usd, notes: project.notes, ...patch,
    };
    await api.put(`/projects/${id}`, payload);
    // Code / CNY rate changes move line costs and references.
    await refreshLineData();
  };

  const download = async (kind) => {
    if (dirty && !(await doSave())) return;
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
      let detail = err?.response?.data?.detail;
      // a 422 during export comes back as a JSON blob even on a blob request
      if (!detail && err?.response?.data instanceof Blob) {
        try { detail = JSON.parse(await err.response.data.text())?.detail; } catch { /* ignore */ }
      }
      setError(detail || "Export failed. Add at least one estimate line first.");
    }
  };

  const deleteProject = async () => {
    if (!confirm(`Delete "${project.name}"? This removes all its locations and estimate lines and cannot be undone.`)) return;
    setError("");
    try {
      await api.delete(`/projects/${id}`);
      navigate("/");
    } catch (err) {
      setError(errorText(err, "Could not delete the project."));
    }
  };

  if (!project) {
    return error
      ? <div className="text-xs text-red-600">{error} <button onClick={load} className="text-ruby hover:underline">Retry</button></div>
      : <div className="text-ink/40 text-sm">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs text-ruby hover:underline">&larr; All projects</Link>
        <div className="flex items-start justify-between mt-1">
          <div>
            <h1 className="text-xl font-semibold text-ink">
              {project.name}
              {project.code && <span className="text-ink/40 font-normal"> ({project.code})</span>}
            </h1>
            <div className="text-xs text-ink/60 mt-1">
              <span className="text-[10px] uppercase tracking-wide text-ink/70 bg-ink/5 px-1.5 py-0.5 rounded mr-1">
                {typeLabel(project.project_type)}
              </span>
              {project.country.name}
              {project.start_date && <> &middot; {project.start_date} &rarr; {project.end_date}</>} &middot; margin {project.default_margin_pct}%
              {project.selling_company && <> &middot; sold via {project.selling_company.name}</>}
              {project.country.is_template && (
                <span className="ml-2 text-amber-600 font-medium">country data not yet configured</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
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
            <button onClick={() => download("product-import")} className="text-sm px-3 py-2 rounded-md border bg-white hover:bg-slate-50">
              Export Product Import for Odoo (.zip)
            </button>
            {currentUser?.is_admin && (
              <button onClick={deleteProject} title="Delete project"
                className="text-sm px-3 py-2 rounded-md border border-red-200 text-red-600 bg-white hover:bg-red-50">
                Delete project
              </button>
            )}
          </div>
        </div>
        {dirty && !saving && (
          <div className="text-xs text-amber-600 mt-2">Unsaved changes -- click Save to persist them.</div>
        )}
        {error && <div className="text-xs text-red-600 mt-2">{error}</div>}

        <ProjectMetaEditor project={project} sellingCompanies={sellingCompanies} onSave={saveProjectMeta} />
      </div>

      {summary && (
        <div className={`grid grid-cols-2 gap-3 ${showLabor ? "sm:grid-cols-5" : "sm:grid-cols-4"}`}>
          <SummaryStat label="Material cost" value={money(summary.material_total)} />
          {showLabor && <SummaryStat label="Labor cost" value={money(summary.labor_total)} />}
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
            products={visibleProducts}
            supportItems={supportItems}
            showLabor={showLabor}
            costMap={costMap}
            lineDataById={lineDataById}
            project={project}
            componentsByLineId={componentsByLineId}
            onRemoveLocation={() => removeLocation(loc.id)}
            onAddLine={(line) => addLine(loc.id, line)}
            onUpdateLine={updateLine}
            onRemoveLine={removeLine}
            onSaveComponentCode={saveComponentCode}
            onAddComponent={addComponent}
            onUpdateComponent={updateComponent}
            onDeleteComponent={deleteComponent}
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

function ProjectMetaEditor({ project, sellingCompanies, onSave }) {
  const furniture = bomPerLine(project.project_type);
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState(project.code || "");
  const [sellingCompanyId, setSellingCompanyId] = useState(project.selling_company_id || "");
  const [cny, setCny] = useState(project.cny_per_usd ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setCode(project.code || "");
    setSellingCompanyId(project.selling_company_id || "");
    setCny(project.cny_per_usd ?? "");
  }, [project.id, project.code, project.selling_company_id, project.cny_per_usd]);

  if (!open) {
    return (
      <div className="mt-2">
        {!project.code && (
          <div className="text-xs text-amber-600 mb-1">
            This project has no code yet -- set one before exporting (it prefixes every item code).
          </div>
        )}
        <button onClick={() => setOpen(true)} className="text-xs text-ruby hover:underline">
          Edit project code / selling company{furniture ? " / CNY rate" : ""}
        </button>
      </div>
    );
  }

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const patch = { code: code.trim(), selling_company_id: sellingCompanyId ? Number(sellingCompanyId) : null };
      if (furniture) patch.cny_per_usd = cny === "" ? null : Number(cny);
      await onSave(patch);
      setOpen(false);
    } catch (err) {
      setError(errorText(err, "Could not save the project."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2 mt-2 bg-white border rounded-md p-3">
      <div>
        <label className="text-xs text-ink/60">Project code *</label>
        <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. FLH" className="w-32 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div>
        <label className="text-xs text-ink/60">Selling company</label>
        <select value={sellingCompanyId} onChange={(e) => setSellingCompanyId(e.target.value)} className="border rounded-md px-2 py-1.5 text-sm">
          <option value="">--</option>
          {sellingCompanies.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>
      {furniture && (
        <div>
          <label className="text-xs text-ink/60">CNY per USD</label>
          <input type="number" step="0.01" value={cny} onChange={(e) => setCny(e.target.value)} placeholder="7.20" className="w-24 border rounded-md px-2 py-1.5 text-sm" />
        </div>
      )}
      <button disabled={saving} className="text-sm px-3 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Saving..." : "Save"}
      </button>
      <button type="button" onClick={() => setOpen(false)} className="text-sm px-3 py-1.5 rounded-md border bg-white">
        Cancel
      </button>
      {error && <div className="w-full text-xs text-red-600">{error}</div>}
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

function LocationBlock({ location, lines, products, supportItems, showLabor, costMap, lineDataById, project, componentsByLineId, onRemoveLocation, onAddLine, onUpdateLine, onRemoveLine, onSaveComponentCode, onAddComponent, onUpdateComponent, onDeleteComponent }) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const furniture = bomPerLine(project.project_type);
  const total = lines.reduce((s, l) => s + lineCosts(l, costMap, project, lineDataById).costTotal, 0);
  const productById = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p])), [products]);
  const editColSpan = showLabor ? 8 : 7;

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
              <th className="px-2 py-2 font-normal">Item code</th>
              <th className="px-2 py-2 font-normal text-right">Qty</th>
              <th className="px-2 py-2 font-normal text-right">Material/unit</th>
              {showLabor && <th className="px-2 py-2 font-normal text-right">Labor/unit</th>}
              <th className="px-2 py-2 font-normal text-right">Margin</th>
              <th className="px-2 py-2 font-normal text-right">Line total</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => {
              const product = productById[l.product_id];
              const c = lineCosts(l, costMap, project, lineDataById);
              const components = componentsByLineId[l.id] || [];
              const isTempLine = typeof l.id === "string";
              const fwMissing = furniture && components.length > 0 && !(l.factory_work_cost_cny > 0);
              const bomMissing = furniture && !isTempLine && components.length === 0;
              return editingId === l.id ? (
                <tr key={l.id} className="border-b last:border-0">
                  <td colSpan={editColSpan}>
                    <LineItemForm
                      products={products}
                      showLabor={showLabor}
                      furniture={furniture}
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
                <Fragment key={l.id}>
                  <tr className="border-b last:border-0 hover:bg-slate-50 cursor-pointer" onClick={() => setEditingId(l.id)}>
                    <td className="px-4 py-2">
                      {product?.name || `#${l.product_id}`}
                      {c.needsSetup && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                          needs setup
                        </span>
                      )}
                      {bomMissing && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                          no BOM
                        </span>
                      )}
                      {fwMissing && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                          no factory work $
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-ink/60" title="Odoo reference: project code + item code">
                      {referenceCode(project.code, l.item_code) || <span className="text-ink/30">--</span>}
                    </td>
                    <td className="px-2 py-2 text-right">{num(l.qty, 1)} {product?.uom}</td>
                    <td className="px-2 py-2 text-right">{money(c.materialPerUnit)}</td>
                    {showLabor && <td className="px-2 py-2 text-right">{money(c.laborPerUnit)}</td>}
                    <td className="px-2 py-2 text-right">{l.margin_pct_override != null ? `${l.margin_pct_override}%` : "default"}</td>
                    <td className="px-2 py-2 text-right font-medium">{money(c.costTotal)}</td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      {!isTempLine && (furniture || components.length > 0) && (
                        <button
                          onClick={(e) => { e.stopPropagation(); setExpandedId(expandedId === l.id ? null : l.id); }}
                          className="text-xs text-ink/50 hover:underline mr-2"
                        >
                          {expandedId === l.id ? "hide BOM" : furniture ? "BOM" : "BOM codes"}
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); onRemoveLine(l.id); }}
                        className="text-xs text-red-500 hover:underline"
                      >
                        remove
                      </button>
                    </td>
                  </tr>
                  {expandedId === l.id && (
                    <tr className="border-b last:border-0 bg-slate-50">
                      <td colSpan={editColSpan} className="px-4 py-3">
                        {furniture ? (
                          <FurnitureBomEditor
                            line={l}
                            product={product}
                            components={components}
                            supportItems={supportItems}
                            cnyPerUsd={project.cny_per_usd || 7.2}
                            onAdd={(payload) => onAddComponent(l.id, payload)}
                            onUpdate={onUpdateComponent}
                            onDelete={onDeleteComponent}
                          />
                        ) : (
                          <BomCodeEditor components={components} onSave={(compId, code) => onSaveComponentCode(l.id, compId, code)} />
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}

      {adding && (
        <div className="p-4 border-t bg-slate-50">
          {furniture && (
            <div className="text-xs text-ink/50 mb-2">
              Add the line, then open its <b>BOM</b> to enter Fabric / Stone / Metal / Accessories quantities and the Factory Work cost.
            </div>
          )}
          <LineItemForm
            products={products}
            showLabor={showLabor}
            furniture={furniture}
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

function FurnitureBomEditor({ line, product, components, supportItems, cnyPerUsd, onAdd, onUpdate, onDelete }) {
  const [adding, setAdding] = useState(false);
  // Only the four furniture BOM categories -- wetworks recipe components
  // (Gypsum board, tile, ...) don't belong on a furniture line.
  const pickable = supportItems.filter((s) => FURNITURE_BOM_CATEGORIES.includes(s.purchase_category));
  const fwCny = line.factory_work_cost_cny || 0;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-medium text-ink/60">
          BOM for this line -- quantities per one {product?.uom || "unit"} of {product?.name || "the product"},
          prices in CNY (¥{num(cnyPerUsd, 2)} / $).
        </div>
        <button onClick={() => setAdding(true)} className="text-xs px-2 py-1 rounded border bg-white hover:bg-slate-100">
          + Component
        </button>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-ink/40 border-b">
            <th className="py-1 font-normal">Support item</th>
            <th className="py-1 font-normal">Item code</th>
            <th className="py-1 font-normal text-right">Qty / unit</th>
            <th className="py-1 font-normal text-right">Price ¥</th>
            <th className="py-1 font-normal text-right">Line total $</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {components.map((c) => (
            <FurnitureBomRow key={c.id} component={c}
              onSave={(patch) => onUpdate(c.id, {
                support_item_id: c.support_item_id, qty_per_unit: c.qty_per_unit,
                unit_price_cny: c.unit_price_cny, item_code: c.item_code, ...patch,
              })}
              onDelete={() => onDelete(c.id)} />
          ))}
          <tr className="border-b last:border-0 text-ink/60">
            <td className="py-1.5">Factory Work for {product?.name}{line.item_code ? ` ${line.item_code}` : ""}</td>
            <td className="py-1.5 text-ink/40">{line.item_code || "--"}</td>
            <td className="py-1.5 text-right">1</td>
            <td className="py-1.5 text-right">
              {fwCny > 0 ? `¥${num(fwCny, 2)}` : <span className="text-amber-600">set in line editor</span>}
            </td>
            <td className="py-1.5 text-right">
              {fwCny > 0 ? money((fwCny / cnyPerUsd) * line.qty) : "--"}
            </td>
            <td></td>
          </tr>
          {components.length === 0 && (
            <tr><td colSpan={6} className="py-2 text-ink/30">No components yet.</td></tr>
          )}
        </tbody>
      </table>
      {adding && (
        <AddComponentForm
          supportItems={pickable}
          existing={components.map((c) => c.support_item_id)}
          onCancel={() => setAdding(false)}
          onSubmit={(payload) => { onAdd(payload); setAdding(false); }}
        />
      )}
    </div>
  );
}

// Item codes: an exported component is support item + code, so the same code
// may repeat across items; the server rejects the same item + code at a
// different price.
function FurnitureBomRow({ component, onSave, onDelete }) {
  const [qty, setQty] = useState(component.qty_per_unit ?? "");
  const [price, setPrice] = useState(component.unit_price_cny ?? "");
  const [code, setCode] = useState(component.item_code || "");
  useEffect(() => {
    setQty(component.qty_per_unit ?? "");
    setPrice(component.unit_price_cny ?? "");
    setCode(component.item_code || "");
  }, [component.qty_per_unit, component.unit_price_cny, component.item_code]);

  return (
    <tr className="border-b last:border-0">
      <td className="py-1.5">
        {component.support_item.name}
        <span className="text-ink/40"> · {component.support_item.purchase_category || "--"}</span>
      </td>
      <td className="py-1.5">
        <input value={code} onChange={(e) => setCode(e.target.value)}
          onBlur={() => code.trim() && code !== (component.item_code || "") && onSave({ item_code: code.trim() })}
          placeholder="e.g. FAB-01"
          className="w-24 border rounded px-1.5 py-1 text-xs" />
      </td>
      <td className="py-1.5 text-right">
        <input type="number" step="0.0001" value={qty}
          onChange={(e) => setQty(e.target.value)}
          onBlur={() => qty !== "" && Number(qty) !== component.qty_per_unit && onSave({ qty_per_unit: Number(qty) })}
          className="w-16 border rounded px-1.5 py-1 text-xs text-right" />
        {" "}{component.support_item.uom}
      </td>
      <td className="py-1.5 text-right">
        <input type="number" step="0.01" value={price}
          onChange={(e) => setPrice(e.target.value)}
          onBlur={() => price !== "" && Number(price) > 0 && Number(price) !== component.unit_price_cny && onSave({ unit_price_cny: Number(price) })}
          className="w-20 border rounded px-1.5 py-1 text-xs text-right" />
      </td>
      <td className="py-1.5 text-right">{money(component.total_cost)}</td>
      <td className="py-1.5 text-right">
        <button onClick={onDelete} className="text-red-500 hover:underline">remove</button>
      </td>
    </tr>
  );
}

function AddComponentForm({ supportItems, existing, onCancel, onSubmit }) {
  const [supportItemId, setSupportItemId] = useState("");
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState("");
  const [code, setCode] = useState("");
  const [cat, setCat] = useState("");
  const options = supportItems.filter((s) => !existing.includes(s.id) && (!cat || s.purchase_category === cat));
  const valid = supportItemId && Number(qty) > 0 && Number(price) > 0 && code.trim();

  const submit = (e) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({
      support_item_id: Number(supportItemId), qty_per_unit: Number(qty),
      unit_price_cny: Number(price), item_code: code.trim(),
    });
  };
  return (
    <form onSubmit={submit} className="mt-3 pt-3 border-t flex flex-wrap items-end gap-2">
      <div>
        <label className="text-[11px] text-ink/50">Type</label>
        <select value={cat} onChange={(e) => setCat(e.target.value)} className="border rounded px-1.5 py-1 text-xs">
          <option value="">All</option>
          {FURNITURE_BOM_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="min-w-[180px]">
        <label className="text-[11px] text-ink/50">Support item</label>
        <select required value={supportItemId} onChange={(e) => setSupportItemId(e.target.value)} className="w-full border rounded px-1.5 py-1 text-xs">
          <option value="">Select...</option>
          {options.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.uom})</option>)}
        </select>
      </div>
      <div>
        <label className="text-[11px] text-ink/50">Item code</label>
        <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="FAB-01"
          className="w-24 border rounded px-1.5 py-1 text-xs" />
      </div>
      <div>
        <label className="text-[11px] text-ink/50">Qty / unit</label>
        <input required type="number" step="0.0001" value={qty} onChange={(e) => setQty(e.target.value)} className="w-16 border rounded px-1.5 py-1 text-xs" />
      </div>
      <div>
        <label className="text-[11px] text-ink/50">Price ¥</label>
        <input required type="number" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} className="w-20 border rounded px-1.5 py-1 text-xs" />
      </div>
      <button disabled={!valid} className="text-xs px-3 py-1.5 rounded bg-ruby text-white hover:bg-ruby-dark disabled:opacity-40">Add</button>
      <button type="button" onClick={onCancel} className="text-xs px-2 py-1.5 rounded border bg-white">Cancel</button>
    </form>
  );
}

function BomCodeEditor({ components, onSave }) {
  return (
    <div>
      <div className="text-xs font-medium text-ink/60 mb-2">
        BOM item codes -- each material exports as project code + this code (just the project code if blank).
      </div>
      <table className="w-full text-xs max-w-2xl">
        <thead>
          <tr className="text-left text-ink/40 border-b">
            <th className="py-1 font-normal">Support item</th>
            <th className="py-1 font-normal text-right">Qty</th>
            <th className="py-1 pl-3 font-normal">Item code</th>
          </tr>
        </thead>
        <tbody>
          {components.map((c) => (
            <BomCodeRow key={c.id} component={c} onSave={(code) => onSave(c.id, code)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BomCodeRow({ component, onSave }) {
  const [value, setValue] = useState(component.item_code || "");
  useEffect(() => setValue(component.item_code || ""), [component.item_code]);
  return (
    <tr className="border-b last:border-0">
      <td className="py-1">{component.support_item.name}</td>
      <td className="py-1 text-right">{num(component.qty, 0)} {component.support_item.uom}</td>
      <td className="py-1 pl-3">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => value !== (component.item_code || "") && onSave(value)}
          placeholder="e.g. PT-01"
          className="w-28 border rounded px-2 py-1 text-xs"
        />
      </td>
    </tr>
  );
}

function LineItemForm({ products, showLabor = true, furniture = false, initial, onCancel, onSubmit }) {
  const [productId, setProductId] = useState(initial?.product_id ?? "");
  const [qty, setQty] = useState(initial?.qty ?? "");
  const [margin, setMargin] = useState(initial?.margin_pct_override ?? "");
  const [drawingNo, setDrawingNo] = useState(initial?.drawing_no ?? "");
  const [remark, setRemark] = useState(initial?.remark ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [dimension, setDimension] = useState(initial?.dimension ?? "");
  const [itemCode, setItemCode] = useState(initial?.item_code ?? "");
  const [factoryWork, setFactoryWork] = useState(initial?.factory_work_cost_cny ?? "");
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
      description: description || null,
      dimension: dimension || null,
      item_code: itemCode || null,
      factory_work_cost_cny: furniture ? (factoryWork === "" ? null : Number(factoryWork)) : null,
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
        <label className="text-xs text-ink/60" title="Exports as project code + item code. Same product + same code = the same product.">
          Item code{furniture ? " *" : ""}
        </label>
        <input value={itemCode} onChange={(e) => setItemCode(e.target.value)}
          placeholder={furniture ? "e.g. CH-01" : "blank = project code"} className="w-28 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      {furniture && (
        <div>
          <label className="text-xs text-ink/60">Factory Work ¥</label>
          <input type="number" step="0.01" value={factoryWork} onChange={(e) => setFactoryWork(e.target.value)} placeholder="per unit, CNY" className="w-24 border rounded-md px-2 py-1.5 text-sm" />
        </div>
      )}
      <div>
        <label className="text-xs text-ink/60">Drawing #</label>
        <input value={drawingNo} onChange={(e) => setDrawingNo(e.target.value)} className="w-24 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div>
        <label className="text-xs text-ink/60">Dimension</label>
        <input value={dimension} onChange={(e) => setDimension(e.target.value)} className="w-24 border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div className="flex-1 min-w-[140px]">
        <label className="text-xs text-ink/60">Remark</label>
        <input value={remark} onChange={(e) => setRemark(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <div className="flex-1 min-w-[140px]">
        <label className="text-xs text-ink/60">Description</label>
        <input value={description} onChange={(e) => setDescription(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
      </div>
      <button className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {initial ? "Save line" : "Add"}
      </button>
      <button type="button" onClick={onCancel} className="text-sm px-3 py-1.5 rounded-md border bg-white">
        Cancel
      </button>
      {selected?.needs_setup && (
        <div className="text-xs text-amber-600 w-full">
          This product has no {showLabor ? "coverage/BOM" : "BOM"} data yet -- cost will show as $0 until an admin configures it
          {" "}(and a material price is set for the project's country).
        </div>
      )}
    </form>
  );
}
