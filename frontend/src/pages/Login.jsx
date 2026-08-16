import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { setToken } from "../auth";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const res = await api.post("/auth/login", { username, password });
      setToken(res.data.access_token);
      navigate("/");
    } catch (err) {
      setError(err?.response?.data?.detail || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream">
      <form onSubmit={submit} className="bg-white border rounded-lg shadow-sm w-full max-w-sm p-6 space-y-4">
        <div className="text-center">
          <img src="/ifield-logo.png" alt="i-field" className="h-7 w-auto mx-auto mb-3" />
          <h1 className="text-lg font-display font-semibold text-ink">Wetworks Estimator</h1>
        </div>
        <div>
          <label className="text-xs text-ink/60">Username</label>
          <input
            required
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full border rounded-md px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-ink/60">Password</label>
          <input
            required
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border rounded-md px-3 py-2 text-sm"
          />
        </div>
        {error && <div className="text-xs text-red-600">{error}</div>}
        <button disabled={submitting} className="w-full py-2 text-sm rounded-md bg-ruby text-white hover:bg-ruby-dark">
          {submitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
