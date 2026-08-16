import { useEffect, useState } from "react";
import api from "../api";
import { useCurrentUser } from "../components/RequireAuth";

export default function AdminUsers() {
  const currentUser = useCurrentUser();
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");

  const load = () => {
    api.get("/users").then((r) => setUsers(r.data)).catch(() => setError("Admin access required."));
  };
  useEffect(load, []);

  if (!currentUser?.is_admin) {
    return <div className="text-sm text-ink/60 bg-white border rounded-lg p-6">Admin access required.</div>;
  }
  if (error) return <div className="text-sm text-red-600">{error}</div>;
  if (!users) return <div className="text-ink/40 text-sm">Loading...</div>;

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-xl font-semibold text-ink">Users</h1>
      <div className="bg-white border rounded-lg divide-y">
        {users.map((u) => (
          <UserRow key={u.id} user={u} />
        ))}
      </div>
      <NewUserForm onCreated={load} />
    </div>
  );
}

function UserRow({ user }) {
  const [changing, setChanging] = useState(false);
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.put(`/users/${user.id}/password`, { new_password: password });
      setPassword("");
      setChanging(false);
      setDone(true);
      setTimeout(() => setDone(false), 3000);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to change password");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-4 py-2.5 text-sm">
      <div className="flex items-center justify-between">
        <span>{user.username}</span>
        <div className="flex items-center gap-3">
          {done && <span className="text-xs text-emerald-600">Password updated</span>}
          {user.is_admin && (
            <span className="text-[10px] uppercase tracking-wide text-ruby bg-ruby-tint px-1.5 py-0.5 rounded">
              admin
            </span>
          )}
          <button onClick={() => setChanging((v) => !v)} className="text-xs text-ink/50 hover:text-ruby">
            {changing ? "cancel" : "change password"}
          </button>
        </div>
      </div>
      {changing && (
        <form onSubmit={submit} className="flex items-center gap-2 mt-2">
          <input
            required
            type="password"
            placeholder="New password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="flex-1 border rounded-md px-2 py-1.5 text-sm"
          />
          <button disabled={saving} className="text-xs px-3 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
            {saving ? "Saving..." : "Save"}
          </button>
        </form>
      )}
      {error && <div className="text-xs text-red-600 mt-1">{error}</div>}
    </div>
  );
}

function NewUserForm({ onCreated }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.post("/users", { username, password, is_admin: isAdmin });
      setUsername("");
      setPassword("");
      setIsAdmin(false);
      onCreated();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to create user");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="bg-white border rounded-lg p-4 space-y-3">
      <h2 className="font-medium text-ink text-sm">+ New user</h2>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-ink/60">Username</label>
          <input required value={username} onChange={(e) => setUsername(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
        </div>
        <div>
          <label className="text-xs text-ink/60">Password</label>
          <input required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border rounded-md px-2 py-1.5 text-sm" />
        </div>
      </div>
      <label className="flex items-center gap-2 text-xs text-ink/60">
        <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
        Admin (can see every user's projects)
      </label>
      {error && <div className="text-xs text-red-600">{error}</div>}
      <button disabled={saving} className="text-sm px-4 py-1.5 rounded-md bg-ruby text-white hover:bg-ruby-dark">
        {saving ? "Creating..." : "Create user"}
      </button>
    </form>
  );
}
