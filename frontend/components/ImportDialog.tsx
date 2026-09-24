"use client";

import { useEffect, useState } from "react";
import { api, ApiError, Category, DocumentPreview, DocumentRow, ImportMapping, ImportPreview, ImportResult, Wallet } from "@/lib/api";
import { useElapsed } from "@/lib/useElapsed";

const DATE_FORMATS = ["YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY"];

type ReviewRow = DocumentRow & { include: boolean };

const isCsv = (file: File) => file.name.toLowerCase().endsWith(".csv") || file.type === "text/csv";

export default function ImportDialog({
  wallets,
  categories,
  onClose,
  onImported,
}: {
  wallets: Wallet[];
  categories: Category[];
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
  const [reading, setReading] = useState(false);
  const readSeconds = useElapsed(reading);
  const [review, setReview] = useState<ReviewRow[] | null>(null);
  const [documentType, setDocumentType] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function readDocument(chosen: File) {
    setFile(chosen);
    setPreview(null);
    setReview(null);
    setError("");
    setBusy(true);
    setReading(true);
    const form = new FormData();
    form.append("file", chosen);
    try {
      const doc = await api<DocumentPreview>("/import/document/preview", { method: "POST", body: form });
      setDocumentType(doc.document_type);
      setReview(doc.transactions.map((t) => ({ ...t, include: true })));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The document could not be read. Check that TracepAI is running.");
    } finally {
      setBusy(false);
      setReading(false);
    }
  }

  async function importReviewed() {
    if (!review) return;
    setError("");
    setBusy(true);
    try {
      const transactions = review.filter((r) => r.include).map(({ include: _, ...row }) => row);
      setResult(await api<ImportResult>("/import/document", { method: "POST", json: { wallet_id: Number(walletId), transactions } }));
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The import failed. Check that TracepAI is running.");
    } finally {
      setBusy(false);
    }
  }

  const updateRow = (i: number, change: Partial<ReviewRow>) =>
    setReview((rows) => rows && rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const included = review?.filter((r) => r.include).length ?? 0;

  async function loadPreview(chosen: File) {
    setFile(chosen);
    setReview(null);
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
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-panel p-6 sm:rounded-3xl ${review?.length ? "sm:max-w-4xl" : "sm:max-w-2xl"}`}
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 id="import-title" className="font-display text-xl font-semibold">
            Import transactions
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
                Statement, receipt or CSV
                <input
                  className="field mt-1"
                  type="file"
                  accept=".csv,text/csv,application/pdf,image/*"
                  disabled={busy}
                  onChange={(e) => {
                    const chosen = e.target.files?.[0];
                    if (chosen) (isCsv(chosen) ? loadPreview : readDocument)(chosen);
                  }}
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

            {reading && (
              <p role="status" className="flex items-center gap-2 text-sm text-ink-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-accent motion-reduce:animate-none" />
                Reading with qwen3-vl, {readSeconds}s. Statements take about a minute per page.
              </p>
            )}

            {review && (
              <>
                <p className="text-sm text-ink-2">
                  {review.length === 0
                    ? "No transactions were found in this file."
                    : `Found ${review.length} ${review.length === 1 ? "transaction" : "transactions"}${
                        documentType === "bank_statement" ? " in this statement" : ""
                      }. Check them, fix anything that was misread, and untick rows you don't want.`}
                </p>
                {review.length > 0 && (
                  <div className="rounded-xl border border-line text-sm">
                    <div className="hidden gap-2 border-b border-line bg-panel-sunk px-3 py-2 text-xs text-ink-2 sm:flex">
                      <span className="w-4 shrink-0" />
                      <div className="grid flex-1 grid-cols-[9rem_1fr_6.5rem_5rem_10rem] gap-2">
                        <span>Date</span>
                        <span>Description</span>
                        <span>Amount</span>
                        <span>In or out</span>
                        <span>Category</span>
                      </div>
                    </div>
                    <ul className="divide-y divide-line">
                      {review.map((r, i) => (
                        <li key={i} className={`flex items-start gap-2 px-3 py-2 ${r.include ? "" : "opacity-50"}`}>
                          <input
                            className="mt-2.5 h-4 w-4 shrink-0"
                            type="checkbox"
                            aria-label={`Include row ${i + 1}`}
                            checked={r.include}
                            onChange={(e) => updateRow(i, { include: e.target.checked })}
                          />
                          <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-[9rem_1fr_6.5rem_5rem_10rem]">
                            <input
                              className="field px-2 py-1.5"
                              type="date"
                              aria-label={`Row ${i + 1} date`}
                              value={r.date ?? ""}
                              onChange={(e) => updateRow(i, { date: e.target.value || null })}
                            />
                            <input
                              className="field px-2 py-1.5"
                              aria-label={`Row ${i + 1} description`}
                              value={r.merchant}
                              onChange={(e) => updateRow(i, { merchant: e.target.value })}
                            />
                            <input
                              className="field px-2 py-1.5 tnum"
                              type="number"
                              inputMode="decimal"
                              step="0.01"
                              min="0.01"
                              aria-label={`Row ${i + 1} amount`}
                              value={r.amount}
                              onChange={(e) => updateRow(i, { amount: Number(e.target.value) })}
                            />
                            <select
                              className="field px-2 py-1.5"
                              aria-label={`Row ${i + 1} in or out`}
                              value={r.kind}
                              onChange={(e) => updateRow(i, { kind: e.target.value as ReviewRow["kind"], category_id: null })}
                            >
                              <option value="expense">Out</option>
                              <option value="income">In</option>
                            </select>
                            <select
                              className="field col-span-2 px-2 py-1.5 sm:col-span-1"
                              aria-label={`Row ${i + 1} category`}
                              value={r.category_id ?? ""}
                              onChange={(e) => updateRow(i, { category_id: e.target.value ? Number(e.target.value) : null })}
                            >
                              <option value="">Uncategorized</option>
                              {categories
                                .filter((c) => c.kind === r.kind)
                                .map((c) => (
                                  <option key={c.id} value={c.id}>
                                    {c.name}
                                  </option>
                                ))}
                            </select>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}

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
            {review ? (
              <button className="btn btn-primary w-full py-2.5" disabled={!included || busy} onClick={importReviewed}>
                {busy ? "Working" : `Import ${included} ${included === 1 ? "transaction" : "transactions"}`}
              </button>
            ) : (
              <button className="btn btn-primary w-full py-2.5" disabled={!ready || busy} onClick={runImport}>
                {reading ? "Reading" : busy ? "Working" : preview ? `Import ${preview.row_count} rows` : "Choose a file to preview"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
