"use client";

import { useEffect, useState } from "react";
import { api, ApiError, ProfileImportResult } from "@/lib/api";

export default function ProfileImportModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [mode, setMode] = useState<"replace" | "merge">("replace");
  const [result, setResult] = useState<ProfileImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleFileChange(chosen: File) {
    setFile(chosen);
    setError("");
    setSummary(null);

    try {
      const text = await chosen.text();
      const parsed = JSON.parse(text);
      if (!parsed.wallets || !parsed.categories) {
        setError("This file does not appear to be a valid TracepAI profile export.");
        return;
      }
      const wCount = parsed.wallets?.length ?? 0;
      const cCount = parsed.categories?.length ?? 0;
      const tCount = parsed.transactions?.length ?? 0;
      const gCount = parsed.goals?.length ?? 0;
      const bCount = parsed.budgets?.length ?? 0;
      const rCount = parsed.recurring_rules?.length ?? 0;
      setSummary(
        `Profile contains: ${wCount} wallets, ${cCount} categories, ${bCount} budgets, ${gCount} goals, ${rCount} recurring rules, and ${tCount} transactions.`
      );
    } catch {
      setError("Failed to parse JSON file. Ensure you selected a valid .json file.");
    }
  }

  async function runImport() {
    if (!file) return;
    setError("");
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("mode", mode);

    try {
      const res = await api<ProfileImportResult>("/import/profile", {
        method: "POST",
        body: form,
      });
      setResult(res);
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The profile import failed. Please check the file and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-import-title"
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-panel p-6 sm:rounded-3xl sm:max-w-xl"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 id="profile-import-title" className="font-display text-xl font-semibold">
            Import account profile
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-ink-2 hover:text-ink">
            {result ? "Close" : "Cancel"}
          </button>
        </div>

        {result ? (
          <div className="space-y-4">
            <div className="rounded-xl bg-accent-soft p-4 text-ink">
              <p className="font-semibold text-lg">Profile restored successfully!</p>
              <ul className="mt-2 space-y-1 text-sm text-ink-2">
                <li>Wallets: {result.imported.wallets}</li>
                <li>Categories: {result.imported.categories}</li>
                <li>Budgets: {result.imported.budgets}</li>
                <li>Goals: {result.imported.goals}</li>
                <li>Recurring rules: {result.imported.recurring_rules}</li>
                <li>Transactions: {result.imported.transactions}</li>
              </ul>
            </div>
            <button
              type="button"
              className="btn btn-primary w-full"
              onClick={() => {
                onClose();
                window.location.reload();
              }}
            >
              Finish and refresh
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            <p className="text-sm text-ink-2">
              Restore your complete account setup from a TracepAI profile JSON file. This recreates your wallets,
              categories, budgets, goals, recurring rules, and transaction history.
            </p>

            <label className="block">
              <span className="text-sm font-medium">Profile backup file (.json)</span>
              <input
                type="file"
                accept=".json,application/json"
                className="mt-1 block w-full text-sm text-ink-2 file:mr-4 file:rounded-full file:border-0 file:bg-accent-soft file:px-4 file:py-2 file:text-sm file:font-semibold file:text-ink hover:file:brightness-105"
                onChange={(e) => e.target.files?.[0] && handleFileChange(e.target.files[0])}
              />
            </label>

            {summary && (
              <div className="rounded-xl bg-accent-soft/40 p-3 text-sm text-ink">
                {summary}
              </div>
            )}

            <div className="space-y-2">
              <span className="block text-sm font-medium">Restore Mode</span>
              <label className="flex items-start gap-3 rounded-xl border border-ink/10 p-3 cursor-pointer hover:bg-accent-soft/20">
                <input
                  type="radio"
                  name="import-mode"
                  value="replace"
                  checked={mode === "replace"}
                  onChange={() => setMode("replace")}
                  className="mt-1"
                />
                <div>
                  <span className="block text-sm font-semibold">Replace existing data (Recommended)</span>
                  <span className="block text-xs text-ink-2">
                    Clears default placeholder wallets and categories to recreate the exact setup from the backup.
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-3 rounded-xl border border-ink/10 p-3 cursor-pointer hover:bg-accent-soft/20">
                <input
                  type="radio"
                  name="import-mode"
                  value="merge"
                  checked={mode === "merge"}
                  onChange={() => setMode("merge")}
                  className="mt-1"
                />
                <div>
                  <span className="block text-sm font-semibold">Merge with existing data</span>
                  <span className="block text-xs text-ink-2">
                    Preserves your current wallets and categories, matching by name and appending transactions.
                  </span>
                </div>
              </label>
            </div>

            {error && <p className="text-sm text-red-500">{error}</p>}

            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="btn" onClick={onClose} disabled={busy}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={runImport}
                disabled={!file || Boolean(error) || busy}
              >
                {busy ? "Restoring profile..." : "Restore Profile"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
