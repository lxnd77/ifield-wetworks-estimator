import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../api";
import { PROJECT_TYPES, typeLabel, laborApplies } from "../projectTypes";

export default function AdminProductDetail() {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [supportItems, setSupportItems] = useState([]);
  const [countries, setCountries] = useState([]);
  const [countryId, setCountryId] = useState("");
  const [prices, setPrices] = useState({});
  const [purchasingCompanies, setPurchasingCompanies] = useState([]);
  const [vendors, setVendors] = useState([]);

  const load = () => {
    api.get(`/products/${id}`).then((r) => setProduct(r.data));
    api.get("/support-items").then((r) => setSupportItems(r.data));
    api.get("/countries").then((r) => setCountries(r.data));
    api.get("/purchasing-companies").then((r) => setPurchasingCompanies(r.data));
    api.get("/vendors").then((r) => setVendors(r.data));
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

  // Shared save path for all product-level fields (purchasing route,
  // markup) -- always sends the full current product state so one editor's
  // save can't clobber a field owned by another.
  const saveProduct = async (overrides) => {
    await api.put(`/products/${product.id}`, {
      name: product.name, uom: product.uom, category: product.category,
      product_type: product.product_type,
      default_code: product.default_code, odoo_id: product.odoo_id, notes: product.notes,
      purchasing_company_id: product.purchasing_company_id,
      default_vendor_id: product.default_vendor_id,
      consumable_pct: product.consumable_pct, ohp_pct: product.ohp_pct,
      ...overrides,
    });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/admin/products" className="text-xs text-ruby hover:underline">&larr; All products</Link>
        <h1 className="text-xl font-semibold text-slate-800 mt-1">{product.name}</h1>
        <div className="text-xs text-slate-500">{typeLabel(product.product_type)} &middot; {product.category} &middot; {product.uom}</div>
      </div>

      <ProductTypeEditor product={product} onSave={saveProduct} />

      <OdooIdEditor product={product} onSave={saveProduct} />

      <PurchasingRouteEditor product={product} purchasingCompanies={purchasingCompanies} vendors={vendors} onSave={saveProduct} />

      <MaterialMarkupEditor product={product} onSave={saveProduct} />

      {laborApplies(product.product_type) && <CoverageRateEditor product={product} onSaved={load} />}

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

function PurchasingRouteEditor({ product, purchasingCompanies, vendors, onSave }) {
  const [purchasingCompanyId, setPurchasingCompanyId] = useState(product.purchasing_company_id || "");
  const [defaultVendorId, setDefaultVendorId] = useState(product.default_vendor_id || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setPurchasingCompanyId(product.purchasing_company_id || "");
    setDefaultVendorId(product.default_vendor_id || "");
  }, [product.id, product.purchasing_company_id, product.default_vendor_id]);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        purchasing_company_id: purchasingCompanyId ? Number(purchasingCompanyId) : null,
        default_vendor_id: defaultVendorId ? Number(defaultVendorId) : null,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="bg-white border rounded-lg p-4">
      <h2 className="font-medium text-slate-800 mb-1">Purchasing route</h2>
      <p className="text-xs text-slate-500 mb-3">
        Who buys this finished line item. Normally the purchasing company (e.g. I-Field Dubai for Wetworks), which in
        turn buys the BOM materials from each item's own vendor. Set a direct vendor only when this item is bought
        whole, straight from a vendor, bypassing the purchasing company.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500">Purchasing company</label>
          <select value={purchasingCompanyId} onChange={(e) => setPurchasingCompanyId(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm">
            <option value="">--</option>
            {purchasingCompanies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500">Direct vendor override (optional)</label>
          <select value={defaultVendorId} onChange={(e) => setDefaultVendorId(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm">
            <option value="">--</option>
            {vendors.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
        </div>
      </div>
      <button disabled={saving} className="mt-3 text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Saving..." : "Save purchasing route"}
      </button>
    </form>
  );
}

function ProductTypeEditor({ product, onSave }) {
  const [value, setValue] = useState(product.product_type);
  const [saving, setSaving] = useState(false);

  useEffect(() => setValue(product.product_type), [product.id, product.product_type]);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({ product_type: value });
    } finally {
      setSaving(false);
    }
  };

  const dirty = value !== product.product_type;

  return (
    <form onSubmit={save} className="bg-white border rounded-lg p-4">
      <h2 className="font-medium text-slate-800 mb-1">Product type</h2>
      <p className="text-xs text-slate-500 mb-3">
        Which kind of project this product can be added to. Furniture types price on material only --
        their coverage rate (labor) is not used. Changing this hides the product from projects of the old type.
      </p>
      <div className="flex items-end gap-2">
        <select value={value} onChange={(e) => setValue(e.target.value)} className="border rounded-md px-2 py-1.5 text-sm">
          {PROJECT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        {dirty && (
          <button disabled={saving} className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
            {saving ? "Saving..." : "Save type"}
          </button>
        )}
      </div>
    </form>
  );
}

function OdooIdEditor({ product, onSave }) {
  const [odooId, setOdooId] = useState(product.odoo_id || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => setOdooId(product.odoo_id || ""), [product.id, product.odoo_id]);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({ odoo_id: odooId || null });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="bg-white border rounded-lg p-4">
      <h2 className="font-medium text-slate-800 mb-1">Odoo id</h2>
      <p className="text-xs text-slate-500 mb-3">
        Odoo's own product.template external id (e.g. "__export__.product_template_1546_5560096f"), once this
        product has actually been imported into Odoo. Populates the "id" column in exports so a re-import updates
        this record instead of creating a duplicate. Distinct from the item code entered during estimation.
      </p>
      <div className="max-w-md">
        <input
          value={odooId}
          onChange={(e) => setOdooId(e.target.value)}
          placeholder="e.g. __export__.product_template_1546_5560096f"
          className="w-full border rounded-md px-2 py-1.5 text-sm font-mono"
        />
      </div>
      <button disabled={saving} className="mt-3 text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Saving..." : "Save Odoo id"}
      </button>
    </form>
  );
}

function MaterialMarkupEditor({ product, onSave }) {
  const furniture = laborApplies(product.product_type) === false;
  const [consumablePct, setConsumablePct] = useState((product.consumable_pct * 100) ?? 0);
  const [ohpPct, setOhpPct] = useState((product.ohp_pct * 100) ?? 0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setConsumablePct(product.consumable_pct * 100);
    setOhpPct(product.ohp_pct * 100);
  }, [product.id, product.consumable_pct, product.ohp_pct]);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        // Furniture ignores consumable % -- keep it at 0.
        consumable_pct: furniture ? 0 : Number(consumablePct || 0) / 100,
        ohp_pct: Number(ohpPct || 0) / 100,
      });
    } finally {
      setSaving(false);
    }
  };

  const primaryLines = product.bom_lines?.filter((l) => l.role === "primary") || [];

  return (
    <form onSubmit={save} className="bg-white border rounded-lg p-4">
      <h2 className="font-medium text-slate-800 mb-1">{furniture ? "Overhead" : "Material markup"}</h2>
      <p className="text-xs text-slate-500 mb-3">
        {furniture ? (
          <>OHP % (overhead), applied to each furniture estimate line's total (components + Factory Work).</>
        ) : (
          <>
            Consumable % (CMBL) + OHP % (overhead), applied only to this product's primary material line
            {primaryLines.length > 0 && (
              <> ({primaryLines.map((l) => l.support_item.name).join(", ")})</>
            )}
            , matching the source Estimate Form.
          </>
        )}
      </p>
      <div className="grid grid-cols-2 gap-3 max-w-sm">
        {!furniture && (
          <div>
            <label className="text-xs text-slate-500">Consumable % (CMBL)</label>
            <input type="number" step="0.1" value={consumablePct} onChange={(e) => setConsumablePct(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
          </div>
        )}
        <div>
          <label className="text-xs text-slate-500">OHP % (overhead)</label>
          <input type="number" step="0.1" value={ohpPct} onChange={(e) => setOhpPct(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
        </div>
      </div>
      <button disabled={saving} className="mt-3 text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Saving..." : furniture ? "Save overhead" : "Save material markup"}
      </button>
    </form>
  );
}

function CoverageRateEditor({ product, onSaved }) {
  const cr = product.coverage_rate;
  const [form, setForm] = useState({
    primary_coverage_per_day: cr?.primary_coverage_per_day ?? "",
    secondary_coverage_per_day: cr?.secondary_coverage_per_day ?? 0,
    inhouse_count: cr?.inhouse_count ?? 2,
    local_count: cr?.local_count ?? 0,
    inhouse_salary_month_local: cr?.inhouse_salary_month_local ?? 0,
    local_salary_month_local: cr?.local_salary_month_local ?? 0,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm({
      primary_coverage_per_day: cr?.primary_coverage_per_day ?? "",
      secondary_coverage_per_day: cr?.secondary_coverage_per_day ?? 0,
      inhouse_count: cr?.inhouse_count ?? 2,
      local_count: cr?.local_count ?? 0,
      inhouse_salary_month_local: cr?.inhouse_salary_month_local ?? 0,
      local_salary_month_local: cr?.local_salary_month_local ?? 0,
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
        inhouse_salary_month_local: Number(form.inhouse_salary_month_local || 0),
        local_salary_month_local: Number(form.local_salary_month_local || 0),
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
        <Field label="In-house salary / month (local currency)" value={form.inhouse_salary_month_local} onChange={set("inhouse_salary_month_local")} />
        <Field label="Local labor salary / month (local currency)" value={form.local_salary_month_local} onChange={set("local_salary_month_local")} />
      </div>
      <button disabled={saving} className="mt-3 text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
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
  const [editingId, setEditingId] = useState(null);

  const removeLine = async (lineId) => {
    await api.delete(`/bom-lines/${lineId}`);
    onChanged();
  };

  const submitNew = async (payload) => {
    await api.post(`/products/${product.id}/bom-lines`, { ...payload, sort_order: product.bom_lines.length });
    setAdding(false);
    onChanged();
  };

  const submitEdit = async (lineId, payload) => {
    await api.put(`/bom-lines/${lineId}`, payload);
    setEditingId(null);
    onChanged();
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
              <th className="py-1 pr-3 font-normal text-right">Wastage %</th>
              <th className="py-1 pl-3 font-normal">Role</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {product.bom_lines.map((l) =>
              editingId === l.id ? (
                <tr key={l.id} className="border-b last:border-0">
                  <td colSpan={5} className="py-2">
                    <BomLineForm
                      supportItems={supportItems}
                      productUom={product.uom}
                      initial={l}
                      onCancel={() => setEditingId(null)}
                      onSubmit={(payload) => submitEdit(l.id, payload)}
                    />
                  </td>
                </tr>
              ) : (
                <tr key={l.id} className="border-b last:border-0 hover:bg-slate-50 cursor-pointer" onClick={() => setEditingId(l.id)}>
                  <td className="py-1.5">{l.support_item.name}</td>
                  <td className="py-1.5 text-right">{l.qty_per_unit}</td>
                  <td className="py-1.5 pr-3 text-right">{(l.wastage_pct * 100).toFixed(1)}</td>
                  <td className="py-1.5 pl-3">{l.role}</td>
                  <td className="py-1.5 text-right">
                    <button onClick={(e) => { e.stopPropagation(); removeLine(l.id); }} className="text-xs text-red-500 hover:underline">
                      remove
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      )}

      {adding && (
        <div className="mt-4 pt-4 border-t">
          <BomLineForm
            supportItems={supportItems}
            productUom={product.uom}
            onCancel={() => setAdding(false)}
            onSubmit={submitNew}
          />
        </div>
      )}
    </div>
  );
}

function BomLineForm({ supportItems, productUom, initial, onCancel, onSubmit }) {
  const [mode, setMode] = useState("existing");
  const [supportItemId, setSupportItemId] = useState(initial?.support_item_id ?? "");
  const [newName, setNewName] = useState("");
  const [newUom, setNewUom] = useState(productUom);
  const [qty, setQty] = useState(initial?.qty_per_unit ?? "1");
  const [wastage, setWastage] = useState(initial?.wastage_pct ?? "0");
  const [role, setRole] = useState(initial?.role ?? "fixing");
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        qty_per_unit: Number(qty),
        wastage_pct: Number(wastage),
        role,
        sort_order: initial?.sort_order ?? 0,
      };
      if (mode === "existing") payload.support_item_id = Number(supportItemId);
      else {
        payload.new_support_item_name = newName;
        payload.new_support_item_uom = newUom;
      }
      await onSubmit(payload);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2" onClick={(e) => e.stopPropagation()}>
      {!initial && (
        <div className="flex gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input type="radio" checked={mode === "existing"} onChange={() => setMode("existing")} /> Existing support item
          </label>
          <label className="flex items-center gap-1">
            <input type="radio" checked={mode === "new"} onChange={() => setMode("new")} /> New support item
          </label>
        </div>
      )}
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
      <div className="grid grid-cols-3 gap-2">
        <Field label="Qty/unit" value={qty} onChange={(e) => setQty(e.target.value)} required />
        <Field label="Wastage % (0.1 = 10%)" value={wastage} onChange={(e) => setWastage(e.target.value)} />
        <div>
          <label className="text-xs text-slate-500">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm">
            <option value="primary">primary</option>
            <option value="fixing">fixing</option>
          </select>
        </div>
      </div>
      <div className="flex gap-2">
        <button disabled={saving} className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
          {saving ? "Saving..." : initial ? "Save line" : "Add BOM line"}
        </button>
        <button type="button" onClick={onCancel} className="text-sm px-3 py-1.5 rounded-md border">Cancel</button>
      </div>
    </form>
  );
}
