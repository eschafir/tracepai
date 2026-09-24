"use client";

import { useEffect, useState } from "react";
import { api, ApiError, ImportMapping, ImportPreview, ImportResult, Wallet } from "@/lib/api";

const DATE_FORMATS = ["YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY"];

export default function ImportDialog({
  wallets,
  onClose,
  onImported,
}: {
  wallets: Wallet[];
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [walletId, setWalletId] = useState(String(wallets[0]?.id ?? ""));
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [dateFormat, setDateFormat] = useState("YYYY-MM-DD");
  const [split, setSplit] = useState(false);
  const [expensesNegative, setExpensesNegative] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function loadPreview(chosen: File) {
    setFile(chosen);
    setError("");
    setBusy(true);
    const form = new FormData();
    form.append("file", chosen);
    try {
      const p = await api<ImportPreview>("/import/preview", { method: "POST", body: form });
      setPreview(p);
      setMapping(p.mapping);
      setDateFormat(p.date_format);
      setSplit(!p.mapping.amount && Boolean(p.mapping.debit || p.mapping.credit));
    } catch (err) {
      setPreview(null);
      setError(err instanceof ApiError ? err.message : "The file could not be read. Check that TracepAI is running.");
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    if (!file || !mapping) return;
    setError("");
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("wallet_id", walletId);
    form.append("date_format", dateFormat);
    form.append("expenses_negative", String(expensesNegative));
    form.append(
      "mapping",
      JSON.stringify(split ? { ...mapping, amount: null } : { ...mapping, debit: null, credit: null }),
    );
    try {
      setResult(await api<ImportResult>("/import", { method: "POST", body: form }));
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The import failed. Check that TracepAI is running.");
    } finally {
      setBusy(false);
    }
  }

  const column = (field: keyof ImportMapping, label: string) =>
    preview && mapping && (
      <label className="block text-sm font-medium">
        {label}
        <select
          className="field mt-1"
          value={mapping[field] ?? ""}
          onChange={(e) => setMapping({ ...mapping, [field]: e.target.value || null })}
        >
          <option value="">Not in this file</option>
          {preview.headers.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
      </label>
    );

  const ready = mapping?.date && mapping.merchant && (split ? mapping.debit || mapping.credit : mapping.amount);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-panel p-6 sm:max-w-2xl sm:rounded-3xl"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 id="import-title" className="font-display text-xl font-semibold">
            Import a bank statement
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-ink-2 hover:text-ink">
            {result ? "Close" : "Cancel"}
          </button>
        </div>

        {result ? (
          <div className="space-y-3">
            <p className="text-lg">
              Imported {result.imported} {result.imported === 1 ? "transaction" : "transactions"}.
            </p>
            {result.duplicates > 0 && (
              <p className="text-ink-2">Skipped {result.duplicates} already in TracepAI.</p>
            )}
            {result.errors.length > 0 && (
              <div>
                <p className="text-critical">{result.errors.length} rows could not be read:</p>
                <ul className="mt-1 text-sm text-ink-2">
                  {result.errors.slice(0, 5).map((e) => (
                    <li key={e.row}>
                      Row {e.row}: {e.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-sm text-ink-2">Imported rows are tagged #imported, so you can filter and review them.</p>
            <button className="btn btn-primary mt-2 w-full py-2.5" onClick={onClose}>
              Done
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm font-medium">
                CSV file
                <input
                  className="field mt-1"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => e.target.files?.[0] && loadPreview(e.target.files[0])}
                />
              </label>
              <label className="block text-sm font-medium">
                Into wallet
                <select className="field mt-1" value={walletId} onChange={(e) => setWalletId(e.target.value)}>
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {preview && mapping && (
              <>
                <p className="text-sm text-ink-2">
                  {preview.row_count} rows found. Check which column holds what; the guesses come from the column names.
                </p>
                <div className="grid gap-3 sm:grid-cols-3">
                  {column("date", "Date")}
                  {column("merchant", "Description")}
                  <label className="block text-sm font-medium">
                    Date format
                    <select className="field mt-1" value={dateFormat} onChange={(e) => setDateFormat(e.target.value)}>
                      {DATE_FORMATS.map((f) => (
                        <option key={f}>{f}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <fieldset className="flex flex-wrap gap-4 text-sm">
                  <legend className="mb-1 font-medium">Amounts</legend>
                  <label className="flex items-center gap-2">
                    <input type="radio" checked={!split} onChange={() => setSplit(false)} />
                    One amount column
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="radio" checked={split} onChange={() => setSplit(true)} />
                    Separate money out and money in columns
                  </label>
                </fieldset>
                <div className="grid gap-3 sm:grid-cols-2">
                  {split ? (
                    <>
                      {column("debit", "Money out")}
                      {column("credit", "Money in")}
                    </>
                  ) : (
                    <>
                      {column("amount", "Amount")}
                      <label className="flex items-center gap-2 self-end pb-2 text-sm">
                        <input
                          type="checkbox"
                          checked={expensesNegative}
                          onChange={(e) => setExpensesNegative(e.target.checked)}
                        />
                        Spending shows as negative numbers
                      </label>
                    </>
                  )}
                </div>
                <div className="overflow-x-auto rounded-xl border border-line">
                  <table className="w-full text-xs">
                    <thead className="bg-panel-sunk text-left text-ink-2">
                      <tr>
                        {preview.headers.map((h) => (
                          <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, i) => (
                        <tr key={i} className="border-t border-line">
                          {row.map((cell, j) => (
                            <td key={j} className="px-3 py-2 whitespace-nowrap tnum">
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {error && (
              <p role="alert" className="text-sm text-critical">
                {error}
              </p>
            )}
            <button className="btn btn-primary w-full py-2.5" disabled={!ready || busy} onClick={runImport}>
              {busy ? "Working" : preview ? `Import ${preview.row_count} rows` : "Choose a file to preview"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
