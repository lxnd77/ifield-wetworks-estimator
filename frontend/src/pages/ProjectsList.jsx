import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";

export default function ProjectsList() {
  const [projects, setProjects] = useState([]);
  const [countries, setCountries] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const navigate = useNavigate();

  const load = () => {
    api.get("/projects").then((r) => setProjects(r.data));
    api.get("/countries").then((r) => setCountries(r.data));
  };
  useEffect(load, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-slate-800">Projects</h1>
        <button
          onClick={() => setShowNew(true)}
          className="bg-indigo-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-indigo-700"
        >
          + New project
        </button>
      </div>

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
            className="bg-white border rounded-lg p-4 hover:shadow-md transition block"
          >
            <div className="font-medium text-slate-800">{p.name}</div>
            <div className="text-xs text-slate-400 mt-1">
              {p.country?.name} &middot; {p.start_date} &rarr; {p.end_date}
            </div>
            {p.client_name && <div className="text-xs text-slate-500 mt-2">Client: {p.client_name}</div>}
          </Link>
        ))}
      </div>

      {showNew && (
        <NewProjectModal
          countries={countries}
          onClose={() => setShowNew(false)}
          onCreated={(id) => navigate(`/projects/${id}`)}
        />
      )}
    </div>
  );
}

function NewProjectModal({ countries, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "",
    country_id: countries[0]?.id || "",
    client_name: "",
    estimator_name: "",
    start_date: "",
    end_date: "",
    default_margin_pct: 15,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, country_id: Number(form.country_id), default_margin_pct: Number(form.default_margin_pct) };
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
          <label className="text-xs text-slate-500">Project name</label>
          <input required value={form.name} onChange={set("name")} className="w-full border rounded-md px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="text-xs text-slate-500">Country</label>
          <select required value={form.country_id} onChange={set("country_id")} className="w-full border rounded-md px-3 py-2 text-sm">
            {countries.map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.is_template ? " (template - needs data)" : ""}</option>
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
            <label className="text-xs text-slate-500">Start date</label>
            <input type="date" required value={form.start_date} onChange={set("start_date")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-slate-500">End date</label>
            <input type="date" required value={form.end_date} onChange={set("end_date")} className="w-full border rounded-md px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label className="text-xs text-slate-500">Default margin %</label>
          <input type="number" step="0.1" value={form.default_margin_pct} onChange={set("default_margin_pct")} className="w-full border rounded-md px-3 py-2 text-sm" />
        </div>
        {error && <div className="text-xs text-red-600">{error}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-md border">Cancel</button>
          <button disabled={saving} type="submit" className="px-4 py-2 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-700">
            {saving ? "Creating..." : "Create project"}
          </button>
        </div>
      </form>
    </div>
  );
}
