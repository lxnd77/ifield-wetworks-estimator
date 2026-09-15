import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import { useCurrentUser } from "../components/RequireAuth";
import { PROJECT_TYPES, typeConfig, typeLabel } from "../projectTypes";

export default function ProjectsList() {
  const currentUser = useCurrentUser();
  const [projects, setProjects] = useState([]);
  const [countries, setCountries] = useState([]);
  const [sellingCompanies, setSellingCompanies] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const load = () => {
    api.get("/projects").then((r) => setProjects(r.data));
    api.get("/countries").then((r) => setCountries(r.data));
    api.get("/selling-companies").then((r) => setSellingCompanies(r.data));
  };
  useEffect(load, []);

  const deleteProject = async (e, p) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Delete "${p.name}"? This removes all its locations and estimate lines and cannot be undone.`)) return;
    setError("");
    try {
      await api.delete(`/projects/${p.id}`);
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not delete the project.");
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-slate-800">Projects</h1>
        <button
          onClick={() => setShowNew(true)}
          className="bg-ruby text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-ruby-dark"
        >
          + New project
        </button>
      </div>

      {error && <div className="text-xs text-red-600 mb-3">{error}</div>}

      {projects.length === 0 && (
        <div className="text-slate-400 text-sm bg-white border rounded-lg p-8 text-center">
          No projects yet. Create one to start an estimate.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => (
          <Link
            to={`/projects/${p.id}`}
            key={p.id}
            className="bg-white border rounded-lg p-4 hover:shadow-md transition block relative"
          >
            <div className="font-medium text-slate-800 pr-12">
              {p.name} {p.code && <span className="text-slate-400 font-normal">({p.code})</span>}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              <span className="text-slate-500">{typeLabel(p.project_type)}</span> &middot; {p.country?.name}
              {p.start_date && <> &middot; {p.start_date} &rarr; {p.end_date}</>}
              {p.selling_company && <> &middot; sold via {p.selling_company.name}</>}
            </div>
            {p.client_name && <div className="text-xs text-slate-500 mt-2">Client: {p.client_name}</div>}
            {currentUser?.is_admin && p.owner && (
              <div className="text-xs text-ruby mt-1">Owner: {p.owner.username}</div>
            )}
            {currentUser?.is_admin && (
              <button
                onClick={(e) => deleteProject(e, p)}
                title="Delete project"
                className="absolute top-4 right-4 text-xs text-red-500 hover:text-red-700 hover:underline"
              >
                Delete
              </button>
            )}
          </Link>
        ))}
      </div>

      {showNew && (
        <NewProjectModal
          countries={countries}
          sellingCompanies={sellingCompanies}
          onClose={() => setShowNew(false)}
          onCreated={(id) => navigate(`/projects/${id}`)}
        />
      )}
    </div>
  );
}

function NewProjectModal({ countries, sellingCompanies, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "",
    code: "",
    project_type: "wetworks",
    country_id: countries[0]?.id || "",
    selling_company_id: "",
    client_name: "",
    estimator_name: "",
    start_date: "",
    end_date: "",
    default_margin_pct: 15,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const datesRequired = typeConfig(form.project_type).datesRequired;

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        ...form,
        country_id: Number(form.country_id),
        selling_company_id: form.selling_company_id ? Number(form.selling_company_id) : null,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
        default_margin_pct: Number(form.default_margin_pct),
      };
      const res = await api.post("/projects", payload);
      onCreated(res.data.id);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to create project");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-20 p-4">
      <form onSubmit={submit} className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-3">
        <h2 className="text-lg font-semibold text-slate-800">New project</h2>
        <div>
          <label className="text-xs text-slate-500">Project type</label>
          <select value={form.project_type} onChange={set("project_type")} className="w-full border rounded-md px-3 py-2 text-sm">
            {PROJECT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <p className="text-[11px] text-slate-400 mt-1">
            {datesRequired
              ? "Material + labor costing. Only Wetworks products can be added."
              : "Material-only costing (no labor). Only furniture products can be added."}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <label className="text-xs text-slate-500">Project name</label>
            <input required value={form.name} onChange={set("name")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Code *</label>
            <input required value={form.code} onChange={set("code")} placeholder="e.g. FLH" title="Prefixes every item code in the exports"
              className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label className="text-xs text-slate-500">Country</label>
          <select required value={form.country_id} onChange={set("country_id")} className="w-full border rounded-md px-3 py-2 text-sm">
            {countries.map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.is_template ? " (template - needs data)" : ""}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500">Selling company</label>
          <select value={form.selling_company_id} onChange={set("selling_company_id")} className="w-full border rounded-md px-3 py-2 text-sm">
            <option value="">--</option>
            {sellingCompanies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-500">Client name</label>
            <input value={form.client_name} onChange={set("client_name")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Estimator</label>
            <input value={form.estimator_name} onChange={set("estimator_name")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-500">Start date{!datesRequired && " (optional)"}</label>
            <input type="date" required={datesRequired} value={form.start_date} onChange={set("start_date")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-slate-500">End date{!datesRequired && " (optional)"}</label>
            <input type="date" required={datesRequired} value={form.end_date} onChange={set("end_date")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label className="text-xs text-slate-500">Default margin %</label>
          <input type="number" step="0.1" value={form.default_margin_pct} onChange={set("default_margin_pct")} className="w-full border rounded-md px-3 py-2 text-sm" />
        </div>
        {error && <div className="text-xs text-red-600">{error}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-md border">Cancel</button>
          <button disabled={saving} type="submit" className="px-4 py-2 text-sm rounded-md bg-ruby text-white hover:bg-ruby-dark">
            {saving ? "Creating..." : "Create project"}
          </button>
        </div>
      </form>
    </div>
  );
}
