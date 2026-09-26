"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function SignupPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("The passwords don't match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/auth/signup", { method: "POST", json: { username, password } });
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
        <p className="mt-3 mb-10 text-ink-2">Create your account. It starts empty, with a Cash wallet and the usual categories.</p>
        <label className="mb-4 block text-sm font-medium">
          Username
          <input
            className="field mt-1.5"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            minLength={3}
            maxLength={32}
            pattern="[A-Za-z0-9_.\-]+"
            aria-describedby="username-hint"
          />
          <span id="username-hint" className="mt-1 block text-xs font-normal text-ink-2">
            3 to 32 letters, numbers, dots, dashes or underscores. Others use it to share a wallet with you.
          </span>
        </label>
        <label className="mb-4 block text-sm font-medium">
          Password
          <input
            className="field mt-1.5"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            aria-describedby="password-hint"
          />
          <span id="password-hint" className="mt-1 block text-xs font-normal text-ink-2">
            At least 8 characters.
          </span>
        </label>
        <label className="mb-6 block text-sm font-medium">
          Repeat the password
          <input
            className="field mt-1.5"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="mb-4 text-sm text-critical">
            {error}
          </p>
        )}
        <button className="btn btn-primary w-full py-2.5" disabled={busy}>
          {busy ? "Creating your account" : "Create account"}
        </button>
        <p className="mt-6 text-center text-sm text-ink-2">
          Already have an account?{" "}
          <a className="text-accent underline" href="/login/">
            Log in
          </a>
        </p>
      </form>
    </div>
  );
}
