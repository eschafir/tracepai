"use client";

import dynamic from "next/dynamic";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import { PinIcon } from "@/components/LocationField";
import Toast from "@/components/Toast";
import ImportDialog from "@/components/ImportDialog";
import ReceiptViewer, { ReceiptButton } from "@/components/ReceiptViewer";
import ShareStatus from "@/components/ShareStatus";
import TransactionModal from "@/components/TransactionModal";
import { api, Category, Goal, SharedExpense, SharedWallet, Transaction, Wallet, parseShares } from "@/lib/api";
import { money, shortDate, slotColor } from "@/lib/format";

// Leaflet needs the browser's window, so the map only loads on the client.
const SpendingMap = dynamic(() => import("@/components/SpendingMap"), {
  ssr: false,
  loading: () => <p className="p-10 text-center text-ink-2">Loading map</p>,
});

// ?wallet= comes through useSearchParams, not window.location (see app/shared/page.tsx).
export default function TransactionsPage() {
  return (
    <Suspense>
      <TransactionsFromUrl />
    </Suspense>
  );
}

function TransactionsFromUrl() {
  const wallet = useSearchParams().get("wallet") ?? "";
  return <Transactions key={wallet} wallet={wallet} />;
}

function Transactions({ wallet }: { wallet: string }) {
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [filters, setFilters] = useState(() => ({
    q: "",
    category: "",
    start: "",
    end: "",
    tag: "",
    wallet,
  }));
  const [importing, setImporting] = useState(false);
  const [viewing, setViewing] = useState<Transaction | null>(null);
  const [editing, setEditing] = useState<Transaction | "new" | null>(null);
  const [view, setView] = useState<"list" | "map">("list");
  const [deleted, setDeleted] = useState<Transaction | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [shared, setShared] = useState<SharedWallet[]>([]);
  const [myId, setMyId] = useState<number | null>(null);
  const [sharedExpenses, setSharedExpenses] = useState<SharedExpense[]>([]); // shared directly, without a shared wallet

  const load = useCallback(async () => {
    const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    const [txns, cats, ws, gs, sh, me, se] = await Promise.all([
      api<Transaction[]>(`/transactions?${params}`),
      api<Category[]>("/categories"),
      api<Wallet[]>("/wallets"),
      api<Goal[]>("/goals"),
      api<SharedWallet[]>("/shared"),
      api<{ id: number }>("/auth/me"),
      api<SharedExpense[]>("/shared-expenses"),
    ]);
    setTransactions(txns);
    setCategories(cats);
    setWallets(ws);
    setGoals(gs);
    setShared(sh);
    setMyId(me.id);
    setSharedExpenses(se);
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  // Shared expenses use their shared wallet owner's categories.
  const byId = new Map([...shared.flatMap((s) => s.categories), ...categories].map((c) => [c.id, c]));
  const walletName = (id: number | null) => wallets.find((w) => w.id === id)?.name ?? "";
  const currencyOf = (id: number | null) => wallets.find((w) => w.id === id)?.currency;
  // A transfer seen from its destination wallet shows what arrived there.
  const shown = (t: Transaction) =>
    t.to_amount && filters.wallet === String(t.to_wallet_id)
      ? money(t.to_amount, currencyOf(t.to_wallet_id))
      : money(t.amount, currencyOf(t.wallet_id));
  const setFilter = (key: keyof typeof filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setFilters({ ...filters, [key]: e.target.value });

  async function remove(t: Transaction) {
    setTransactions((rows) => rows && rows.filter((r) => r.id !== t.id));
    await api(`/transactions/${t.id}`, { method: "DELETE" });
    setDeleted(t);
    load();
  }

  async function undoDelete() {
    if (!deleted) return;
    const { id: _id, recurring_id: _recurring, ...body } = deleted;
    setDeleted(null);
    await api("/transactions", { method: "POST", json: { ...body, shares: deleted.shared_members ? parseShares(deleted.shared_members) : null } });
    load();
  }

  const clearToast = useCallback(() => setDeleted(null), []);

  const splitOf = (t: Transaction) => sharedExpenses.find((e) => e.id === t.id);
  const sharedWithMe = sharedExpenses.filter((e) => e.paid_by.id !== myId);

  const categoryNames = (t: Transaction) => {
    if (t.kind === "transfer") return `Transfer to ${walletName(t.to_wallet_id)}`;
    const ids = t.splits.length ? t.splits.map((s) => s.category_id) : [t.category_id];
    return ids.map((id) => (id && byId.get(id)?.name) || "Uncategorized").join(", ");
  };

  function actions(t: Transaction) {
    return (
      <>
        <button className="mr-3 text-accent" onClick={() => setEditing(t)}>
          Edit
        </button>
        <button className="text-ink-2 hover:text-critical" onClick={() => remove(t)}>
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
            {p.amount !== null && <span className="text-ink-2 tnum">{money(p.amount, currencyOf(t.wallet_id))}</span>}
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
          Import
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

      <div role="radiogroup" aria-label="View" className="mb-3 flex w-fit gap-1 rounded-full bg-panel p-1 text-sm font-medium">
        {(["list", "map"] as const).map((v) => (
          <button
            key={v}
            role="radio"
            aria-checked={view === v}
            onClick={() => setView(v)}
            className={`rounded-full px-3.5 py-1.5 ${view === v ? "bg-accent text-accent-ink" : "text-ink-2"}`}
          >
            {v === "list" ? "List" : "Map"}
          </button>
        ))}
      </div>

      {sharedWithMe.length > 0 && myId !== null && (
        <section className="mb-4 rounded-2xl bg-panel p-4 sm:p-5">
          <h2 className="mb-3 font-display text-lg font-semibold">Shared with you</h2>
          <ul className="divide-y divide-line text-sm">
            {sharedWithMe.map((e) => {
              const mine = e.shares.find((x) => x.user_id === myId)!;
              return (
                <li key={e.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3 first:pt-0 last:pb-0">
                  <span className="w-14 shrink-0 text-ink-2 tnum">{shortDate(e.date)}</span>
                  <div className="mr-auto min-w-0">
                    <span className="block">{e.merchant || "No merchant"}</span>
                    <span className="block text-xs text-ink-2">
                      {e.paid_by.username} paid {money(e.amount, e.currency)}. Your share is {mine.percent}%.
                    </span>
                    <div className="mt-1">
                      <ShareStatus expense={e} share={mine} myId={myId} wallets={wallets} onChange={load} />
                    </div>
                  </div>
                  <span className="font-medium tnum">{money(mine.amount, e.currency)}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {transactions && (
        <div className="overflow-x-auto rounded-2xl bg-panel">
          {transactions.length === 0 ? (
            <p className="p-10 text-center text-ink-2">
              No transactions match these filters. Clear a filter or add a transaction.
            </p>
          ) : view === "map" ? (
            <SpendingMap transactions={transactions} categories={byId} currencyOf={currencyOf} />
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-ink-2">
                <tr className="border-b border-line">
                  <th className="px-3 py-3 sm:px-4 font-medium">Date</th>
                  <th className="px-3 py-3 sm:px-4 font-medium">Merchant</th>
                  <th className="hidden px-3 py-3 sm:px-4 font-medium sm:table-cell">Category</th>
                  <th className="hidden px-3 py-3 sm:px-4 font-medium md:table-cell">Wallet</th>
                  <th className="hidden px-3 py-3 sm:px-4 font-medium md:table-cell">Tags</th>
                  <th className="hidden px-3 py-3 text-center font-medium sm:table-cell sm:px-4">Receipt</th>
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
                      <span className="flex items-center gap-2">
                        <span>
                          {t.merchant || (
                            <span className="text-ink-2">{t.kind === "transfer" ? "Transfer" : "No merchant"}</span>
                          )}
                        </span>
                        {t.receipt_path && (
                          <span className="sm:hidden">
                            <ReceiptButton label={t.merchant || "this transaction"} onClick={() => setViewing(t)} />
                          </span>
                        )}
                      </span>
                      {t.notes && <span className="block max-w-32 truncate text-xs sm:max-w-56 text-ink-2">{t.notes}</span>}
                      {t.shared_wallet_id && t.shared_members && myId !== null && (
                        <span className="block max-w-32 truncate text-xs sm:max-w-56 text-ink-2">
                          Shared in {shared.find((s) => s.id === t.shared_wallet_id)?.name}, your share{" "}
                          {money((t.amount * (parseShares(t.shared_members)[myId] ?? 0)) / 100, currencyOf(t.wallet_id))}
                        </span>
                      )}
                      {splitOf(t) && myId !== null && (
                        <div className="mt-1 space-y-1">
                          <span className="block text-xs text-ink-2">
                            Your share {money(splitOf(t)!.shares.find((x) => x.user_id === myId)?.amount ?? 0, currencyOf(t.wallet_id))}
                          </span>
                          {splitOf(t)!
                            .shares.filter((x) => x.user_id !== myId)
                            .map((x) => (
                              <ShareStatus key={x.user_id} expense={splitOf(t)!} share={x} myId={myId} wallets={wallets} onChange={load} />
                            ))}
                        </div>
                      )}
                      {t.goal_id && (
                        <span className="block max-w-32 truncate text-xs sm:max-w-56 text-ink-2">
                          Goal: {goals.find((g) => g.id === t.goal_id)?.name}
                        </span>
                      )}
                      {t.place && (
                        <span className="flex items-center gap-1 text-xs text-ink-2">
                          <PinIcon size={12} />
                          <span className="max-w-32 truncate sm:max-w-56">{t.place}</span>
                        </span>
                      )}
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
                    <td className="hidden px-3 py-2 text-center sm:table-cell sm:px-4">
                      {t.receipt_path && (
                        <ReceiptButton label={t.merchant || "this transaction"} onClick={() => setViewing(t)} />
                      )}
                    </td>
                    <td
                      className={`px-3 py-3 text-right font-medium whitespace-nowrap tnum sm:px-4 ${
                        t.kind === "income" ? "text-up" : t.kind === "transfer" ? "text-ink-2" : ""
                      }`}
                    >
                      {sign(t)}
                      {shown(t)}
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
      {deleted && (
        <Toast
          key={deleted.id}
          message={`Deleted ${deleted.merchant || "transaction"}.`}
          action="Undo"
          onAction={undoDelete}
          onDone={clearToast}
        />
      )}
      {viewing?.receipt_path && (
        <ReceiptViewer
          path={viewing.receipt_path}
          title={`${viewing.merchant || "Receipt"}, ${shortDate(viewing.date)}`}
          onClose={() => setViewing(null)}
        />
      )}
      {importing && (
        <ImportDialog
          wallets={wallets}
          categories={categories}
          onClose={() => setImporting(false)}
          onImported={load}
        />
      )}
    </Shell>
  );
}
