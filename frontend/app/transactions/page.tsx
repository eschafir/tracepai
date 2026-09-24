"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import ImportDialog from "@/components/ImportDialog";
import TransactionModal from "@/components/TransactionModal";
import { api, Category, Transaction, Wallet } from "@/lib/api";
import { money, shortDate, slotColor } from "@/lib/format";

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [filters, setFilters] = useState(() => ({
    q: "",
    category: "",
    start: "",
    end: "",
    tag: "",
    wallet: typeof window === "undefined" ? "" : (new URLSearchParams(window.location.search).get("wallet") ?? ""),
  }));
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState<Transaction | "new" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    const [txns, cats, ws] = await Promise.all([
      api<Transaction[]>(`/transactions?${params}`),
      api<Category[]>("/categories"),
      api<Wallet[]>("/wallets"),
    ]);
    setTransactions(txns);
    setCategories(cats);
    setWallets(ws);
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  const byId = new Map(categories.map((c) => [c.id, c]));
  const walletName = (id: number | null) => wallets.find((w) => w.id === id)?.name ?? "";
  const setFilter = (key: keyof typeof filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setFilters({ ...filters, [key]: e.target.value });

  async function remove(id: number) {
    await api(`/transactions/${id}`, { method: "DELETE" });
    setConfirmDelete(null);
    load();
  }

  const categoryNames = (t: Transaction) => {
    if (t.kind === "transfer") return `Transfer to ${walletName(t.to_wallet_id)}`;
    const ids = t.splits.length ? t.splits.map((s) => s.category_id) : [t.category_id];
    return ids.map((id) => (id && byId.get(id)?.name) || "Uncategorized").join(", ");
  };

  function actions(t: Transaction) {
    return confirmDelete === t.id ? (
      <>
        <button className="mr-3 font-medium text-critical" onClick={() => remove(t.id)}>
          Delete
        </button>
        <button className="text-ink-2" onClick={() => setConfirmDelete(null)}>
          Keep
        </button>
      </>
    ) : (
      <>
        <button className="mr-3 text-accent" onClick={() => setEditing(t)}>
          Edit
        </button>
        <button className="text-ink-2 hover:text-critical" onClick={() => setConfirmDelete(t.id)}>
          Delete
        </button>
      </>
    );
  }

  // A transfer only has a direction when looking at one of its wallets.
  function sign(t: Transaction) {
    if (t.kind === "income") return "+";
    if (t.kind === "expense") return "\u2212";
    if (filters.wallet === String(t.to_wallet_id)) return "+";
    if (filters.wallet === String(t.wallet_id)) return "\u2212";
    return "";
  }

  function categoryCell(t: Transaction) {
    if (t.kind === "transfer") return <span className="whitespace-nowrap text-ink-2">Transfer to {walletName(t.to_wallet_id)}</span>;
    const parts = t.splits.length
      ? t.splits.map((s) => ({ category: byId.get(s.category_id), amount: s.amount }))
      : [{ category: t.category_id ? byId.get(t.category_id) : undefined, amount: null }];
    return (
      <ul>
        {parts.map((p, i) => (
          <li key={i} className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="h-2 w-2 rounded-sm" style={{ background: slotColor(p.category?.color_slot) }} />
            {p.category?.name ?? "Uncategorized"}
            {p.amount !== null && <span className="text-ink-2 tnum">{money(p.amount)}</span>}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <Shell
      actions={
        <button className="btn btn-primary" onClick={() => setEditing("new")}>
          Add transaction
        </button>
      }
    >
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <h1 className="mr-auto w-full font-display sm:w-auto text-3xl font-bold tracking-tight">Transactions</h1>
        <button className="btn" onClick={() => setImporting(true)}>
          Import CSV
        </button>
        <a className="btn" href="/api/export?format=csv">
          Export CSV
        </a>
        <a className="btn" href="/api/export?format=json">
          Export JSON
        </a>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 rounded-2xl bg-panel p-4 sm:grid-cols-3 lg:grid-cols-6">
        <label className="col-span-2 text-sm font-medium sm:col-span-1">
          Search
          <input className="field mt-1" placeholder="Merchant or note" value={filters.q} onChange={setFilter("q")} />
        </label>
        <label className="text-sm font-medium">
          Category
          <select className="field mt-1" value={filters.category} onChange={setFilter("category")}>
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium">
          Wallet
          <select className="field mt-1" value={filters.wallet} onChange={setFilter("wallet")}>
            <option value="">All</option>
            {wallets.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium">
          Tag
          <input className="field mt-1" placeholder="vacation" value={filters.tag} onChange={setFilter("tag")} />
        </label>
        <label className="text-sm font-medium">
          From
          <input className="field mt-1" type="date" value={filters.start} onChange={setFilter("start")} />
        </label>
        <label className="text-sm font-medium">
          To
          <input className="field mt-1" type="date" value={filters.end} onChange={setFilter("end")} />
        </label>
      </div>

      {transactions && (
        <div className="overflow-x-auto rounded-2xl bg-panel">
          {transactions.length === 0 ? (
            <p className="p-10 text-center text-ink-2">
              No transactions match these filters. Clear a filter or add a transaction.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-ink-2">
                <tr className="border-b border-line">
                  <th className="px-3 py-3 sm:px-4 font-medium">Date</th>
                  <th className="px-3 py-3 sm:px-4 font-medium">Merchant</th>
                  <th className="hidden px-3 py-3 sm:px-4 font-medium sm:table-cell">Category</th>
                  <th className="hidden px-3 py-3 sm:px-4 font-medium md:table-cell">Wallet</th>
                  <th className="hidden px-3 py-3 sm:px-4 font-medium md:table-cell">Tags</th>
                  <th className="px-3 py-3 sm:px-4 text-right font-medium">Amount</th>
                  <th className="hidden px-3 py-3 sm:px-4 sm:table-cell">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className="border-b border-line last:border-0 hover:bg-panel-sunk">
                    <td className="px-3 py-3 sm:px-4 whitespace-nowrap tnum">{shortDate(t.date)}</td>
                    <td className="px-3 py-3 sm:px-4">
                      {t.merchant || <span className="text-ink-2">{t.kind === "transfer" ? "Transfer" : "No merchant"}</span>}
                      {t.notes && <span className="block max-w-32 truncate text-xs sm:max-w-56 text-ink-2">{t.notes}</span>}
                      <span className="block text-xs text-ink-2 sm:hidden">{categoryNames(t)}</span>
                    </td>
                    <td className="hidden px-3 py-3 sm:px-4 sm:table-cell">{categoryCell(t)}</td>
                    <td className="hidden px-3 py-3 sm:px-4 md:table-cell">{walletName(t.wallet_id)}</td>
                    <td className="hidden px-3 py-3 sm:px-4 text-ink-2 md:table-cell">
                      {t.tags
                        .split(",")
                        .filter(Boolean)
                        .map((tag) => `#${tag}`)
                        .join(" ")}
                    </td>
                    <td
                      className={`px-3 py-3 text-right font-medium whitespace-nowrap tnum sm:px-4 ${
                        t.kind === "income" ? "text-up" : t.kind === "transfer" ? "text-ink-2" : ""
                      }`}
                    >
                      {sign(t)}
                      {money(t.amount)}
                      <div className="mt-1 text-xs font-normal sm:hidden">{actions(t)}</div>
                    </td>
                    <td className="hidden px-3 py-3 sm:px-4 text-right whitespace-nowrap sm:table-cell">{actions(t)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {editing && (
        <TransactionModal
          categories={categories}
          wallets={wallets}
          initial={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {importing && (
        <ImportDialog
          wallets={wallets}
          onClose={() => setImporting(false)}
          onImported={load}
        />
      )}
    </Shell>
  );
}
