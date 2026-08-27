import { useEffect, useState } from "react";
import api from "../api";

const TABS = [
  {
    key: "vendors",
    label: "Vendors",
    endpoint: "/vendors",
    blurb: "External suppliers a BOM item is actually bought from (tile suppliers, paint suppliers, etc). Set on a support item's default vendor.",
    fields: [{ key: "name", label: "Name", required: true }, { key: "notes", label: "Notes" }],
  },
  {
    key: "purchasing-companies",
    label: "Purchasing Companies",
    endpoint: "/purchasing-companies",
    blurb: "I-Field entities that buy a finished line item on behalf of the selling company (e.g. I-Field Dubai for Wetworks). Set as a product's default purchasing route.",
    fields: [
      { key: "name", label: "Name", required: true },
      { key: "country_name", label: "Country" },
      { key: "notes", label: "Notes" },
    ],
  },
  {
    key: "selling-companies",
    label: "Selling Companies",
    endpoint: "/selling-companies",
    blurb: "I-Field entities that invoice the client. Selected per project.",
    fields: [
      { key: "name", label: "Name", required: true },
      { key: "country_name", label: "Country" },
      { key: "notes", label: "Notes" },
    ],
  },
];

export default function AdminSettings() {
  const [activeTab, setActiveTab] = useState(TABS[0].key);
  const tab = TABS.find((t) => t.key === activeTab);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-800">Settings</h1>
      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
              activeTab === t.key ? "text-ruby border-ruby" : "text-slate-500 border-transparent hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <EntityTable key={tab.key} tab={tab} />
    </div>
  );
}

function emptyForm(fields) {
  return Object.fromEntries(fields.map((f) => [f.key, ""]));
}

function EntityTable({ tab }) {
  const [rows, setRows] = useState([]);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");

  const load = () => { api.get(tab.endpoint).then((r) => setRows(r.data)); };
  useEffect(load, [tab.endpoint]);

  const submitNew = async (form) => {
    setError("");
    try {
      await api.post(tab.endpoint, form);
      setAdding(false);
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to save");
    }
  };

  const submitEdit = async (id, form) => {
    setError("");
    try {
      await api.put(`${tab.endpoint}/${id}`, form);
      setEditingId(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to save");
    }
  };

  const remove = async (id) => {
    if (!confirm("Delete this entry?")) return;
    try {
      await api.delete(`${tab.endpoint}/${id}`);
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to delete -- it may still be referenced elsewhere");
    }
  };

  return (
    <div className="bg-white border rounded-lg p-4">
      <div className="flex items-start justify-between mb-3 gap-4">
        <p className="text-xs text-slate-500 max-w-xl">{tab.blurb}</p>
        <button onClick={() => setAdding(true)} className="text-xs px-2 py-1 rounded border hover:bg-slate-50 whitespace-nowrap">
          + Add
        </button>
      </div>
      {error && <div className="text-xs text-red-600 mb-2">{error}</div>}

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-400 border-b">
            {tab.fields.map((f) => (
              <th key={f.key} className="py-1 font-normal pr-3">{f.label}</th>
            ))}
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) =>
            editingId === row.id ? (
              <tr key={row.id} className="border-b last:border-0">
                <td colSpan={tab.fields.length + 1} className="py-2">
                  <EntityForm fields={tab.fields} initial={row} onCancel={() => setEditingId(null)} onSubmit={(f) => submitEdit(row.id, f)} />
                </td>
              </tr>
            ) : (
              <tr key={row.id} className="border-b last:border-0 hover:bg-slate-50 cursor-pointer" onClick={() => setEditingId(row.id)}>
                {tab.fields.map((f) => (
                  <td key={f.key} className="py-1.5 pr-3">{row[f.key] || <span className="text-slate-300">--</span>}</td>
                ))}
                <td className="py-1.5 text-right">
                  <button onClick={(e) => { e.stopPropagation(); remove(row.id); }} className="text-xs text-red-500 hover:underline">
                    remove
                  </button>
                </td>
              </tr>
            )
          )}
          {rows.length === 0 && !adding && (
            <tr>
              <td colSpan={tab.fields.length + 1} className="py-4 text-xs text-slate-400 text-center">
                Nothing here yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {adding && (
        <div className="mt-3 pt-3 border-t">
          <EntityForm fields={tab.fields} onCancel={() => setAdding(false)} onSubmit={submitNew} />
        </div>
      )}
    </div>
  );
}

function EntityForm({ fields, initial, onCancel, onSubmit }) {
  const [form, setForm] = useState(initial ? Object.fromEntries(fields.map((f) => [f.key, initial[f.key] || ""])) : emptyForm(fields));
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = Object.fromEntries(fields.map((f) => [f.key, form[f.key] || null]));
      await onSubmit(payload);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2" onClick={(e) => e.stopPropagation()}>
      {fields.map((f) => (
        <div key={f.key} className="min-w-[160px]">
          <label className="text-xs text-slate-500">{f.label}</label>
          <input required={f.required} value={form[f.key]} onChange={set(f.key)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
        </div>
      ))}
      <button disabled={saving} className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Saving..." : initial ? "Save" : "Add"}
      </button>
      <button type="button" onClick={onCancel} className="text-sm px-3 py-1.5 rounded-md border">Cancel</button>
    </form>
  );
}
