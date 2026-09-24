"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/auth/me").then((res) => res.ok && window.location.replace("/"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", { method: "POST", json: { username, password } });
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Can't reach the server. Check that TracepAI is running.");
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm">
        <h1 className="font-display text-5xl font-bold tracking-tight">
          Tracep<span className="text-accent">AI</span>
        </h1>
        <p className="mt-3 mb-10 text-ink-2">Know where every dollar went.</p>
        <label className="mb-4 block text-sm font-medium">
          Username
          <input
            className="field mt-1.5"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label className="mb-6 block text-sm font-medium">
          Password
          <input
            className="field mt-1.5"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="mb-4 text-sm text-critical">
            {error}
          </p>
        )}
        <button className="btn btn-primary w-full py-2.5" disabled={busy}>
          {busy ? "Logging in" : "Log in"}
        </button>
      </form>
    </div>
  );
}
