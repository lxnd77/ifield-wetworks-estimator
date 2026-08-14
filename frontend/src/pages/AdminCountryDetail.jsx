import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../api";

const FIELD_GROUPS = [
  {
    title: "Currencies & FX (local units per 1 USD)",
    fields: [
      ["site_currency_code", "Site allowance currency", "text"],
      ["site_fx_rate_to_usd", "Site FX rate to USD", "number"],
      ["inhouse_labor_currency_code", "In-house labor currency", "text"],
      ["inhouse_fx_rate_to_usd", "In-house labor FX rate to USD", "number"],
      ["local_labor_currency_code", "Local labor currency", "text"],
      ["local_fx_rate_to_usd", "Local labor FX rate to USD", "number"],
      ["material_currency_code", "Material price currency", "text"],
      ["material_fx_rate_to_usd", "Material FX rate to USD", "number"],
    ],
  },
  {
    title: "Work calendar & overhead",
    fields: [
      ["working_days_per_month", "Working days / month", "number"],
      ["wages_oh_rate_pct", "Wages overhead % (0.15 = 15%)", "number"],
    ],
  },
  {
    title: "Per-worker allowances (monthly, local currency, except where noted)",
    fields: [
      ["food_per_month_local", "Food allowance / month", "number"],
      ["accommodation_per_month_local", "Accommodation / month", "number"],
      ["local_travel_per_month_local", "Local travel / month", "number"],
      ["air_ticket_per_year_local", "Air ticket / year", "number"],
      ["visa_per_year_local", "Visa & insurance / year", "number"],
      ["other_allowance_per_day_usd", "Other allowance / day (USD)", "number"],
    ],
  },
];

export default function AdminCountryDetail() {
  const { id } = useParams();
  const [country, setCountry] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = () => {
    api.get(`/countries/${id}`).then((r) => {
      setCountry(r.data);
      setForm(r.data);
    });
  };
  useEffect(load, [id]);

  if (!country || !form) return <div className="text-slate-400 text-sm">Loading...</div>;

  const set = (k, type) => (e) => setForm({ ...form, [k]: type === "number" ? e.target.value : e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    try {
      const payload = { ...form };
      for (const g of FIELD_GROUPS) {
        for (const [key, , type] of g.fields) {
          if (type === "number") payload[key] = Number(payload[key] || 0);
        }
      }
      const res = await api.put(`/countries/${id}`, payload);
      setCountry(res.data);
      setForm(res.data);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <Link to="/admin/countries" className="text-xs text-ruby hover:underline">&larr; All countries</Link>
        <div className="flex items-center justify-between mt-1">
          <h1 className="text-xl font-semibold text-slate-800">{country.name} ({country.code})</h1>
          {country.is_template && (
            <span className="text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
              needs data
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-1">
          These parameters drive the labor-cost formula for every Wetworks product in this country. Material prices
          per support item are set from each product's page under Products.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-6">
        {FIELD_GROUPS.map((group) => (
          <div key={group.title} className="bg-white border rounded-lg p-4">
            <h2 className="font-medium text-slate-800 mb-3 text-sm">{group.title}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {group.fields.map(([key, label, type]) => (
                <div key={key}>
                  <label className="text-xs text-slate-500">{label}</label>
                  <input
                    type={type}
                    step={type === "number" ? "any" : undefined}
                    value={form[key] ?? ""}
                    onChange={set(key, type)}
                    className="w-full border rounded-md px-2 py-1.5 text-sm"
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="flex items-center gap-3">
          <button disabled={saving} className="text-sm px-4 py-2 rounded-md bg-ruby text-white hover:bg-ruby-dark">
            {saving ? "Saving..." : "Save rate card"}
          </button>
          {saved && <span className="text-xs text-emerald-600">Saved. Existing project estimates in this country will recompute next time they're opened or edited.</span>}
        </div>
      </form>
    </div>
  );
}
