import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";

export default function AdminCountries() {
  const [countries, setCountries] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const navigate = useNavigate();

  const load = () => {
    api.get("/countries").then((r) => setCountries(r.data));
  };
  useEffect(load, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-slate-800">Countries</h1>
        <button onClick={() => setShowNew(true)} className="bg-indigo-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-indigo-700">
          + Add a country
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {countries.map((c) => (
          <Link to={`/admin/countries/${c.id}`} key={c.id} className="bg-white border rounded-lg p-4 hover:shadow-md transition block">
            <div className="flex items-center justify-between">
              <div className="font-medium text-slate-800">{c.name}</div>
              {c.is_template && (
                <span className="text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                  needs data
                </span>
              )}
            </div>
            <div className="text-xs text-slate-400 mt-1">{c.code} &middot; {c.site_currency_code}</div>
          </Link>
        ))}
      </div>

      {showNew && (
        <NewCountryModal onClose={() => setShowNew(false)} onCreated={(id) => navigate(`/admin/countries/${id}`)} />
      )}
    </div>
  );
}

function NewCountryModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const res = await api.post("/countries", { name, code: code.toUpperCase() });
      onCreated(res.data.id);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to create country");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-20 p-4">
      <form onSubmit={submit} className="bg-white rounded-lg shadow-xl w-full max-w-sm p-6 space-y-3">
        <h2 className="text-lg font-semibold text-slate-800">Add a country</h2>
        <p className="text-xs text-slate-500">
          Creates an empty rate-card template you (or an admin) fill in afterward -- labor wages & expenses,
          working days/month, and material prices per support item.
        </p>
        <div>
          <label className="text-xs text-slate-500">Country name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full border rounded-md px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="text-xs text-slate-500">Short code</label>
          <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. UAE" className="w-full border rounded-md px-3 py-2 text-sm" />
        </div>
        {error && <div className="text-xs text-red-600">{error}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-md border">Cancel</button>
          <button disabled={saving} className="px-4 py-2 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-700">
            {saving ? "Creating..." : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
