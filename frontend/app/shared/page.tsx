"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import TransactionModal from "@/components/TransactionModal";
import { Panel } from "@/components/charts";
import { api, ApiError, Category, SharedDetail, Transaction, Wallet } from "@/lib/api";
import { iso, money, shortDate, slotColor } from "@/lib/format";

type Debt = SharedDetail["debts"][number];

// The id comes from the URL through useSearchParams: reading window.location while rendering gets the previous page's
// URL after an in-app navigation, because Next.js updates the address after rendering the new page.
export default function SharedPage() {
  return (
    <Suspense>
      <SharedFromUrl />
    </Suspense>
  );
}

function SharedFromUrl() {
  const id = useSearchParams().get("id") ?? "";
  return <SharedLedger key={id} id={id} />;
}

function SharedLedger({ id }: { id: string }) {
  const [ledger, setLedger] = useState<SharedDetail | null>(null);
  const [me, setMe] = useState("");
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [newMember, setNewMember] = useState("");
  const [settling, setSettling] = useState<{ debt: Debt; amount: string; date: string; wallet: string } | null>(null);
  const [recording, setRecording] = useState<{ id: number; wallet: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [l, who, w, c] = await Promise.all([
        api<SharedDetail>(`/shared/${id}`),
        api<{ username: string }>("/auth/me"),
        api<Wallet[]>("/wallets"),
        api<Category[]>("/categories"),
      ]);
      setLedger(l);
      setMe(who.username);
      setWallets(w);
      setCategories(c);
    } catch {
      setMissing(true);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await load();
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change was not saved. Check that TracepAI is running.");
      return false;
    }
  }

  if (missing) {
    return (
      <Shell>
        <p className="rounded-2xl bg-panel p-8 text-center text-ink-2">
          This shared wallet doesn&apos;t exist, or you&apos;re not a member. <a className="text-accent underline" href="/wallets/">Back to wallets</a>
        </p>
      </Shell>
    );
  }
  if (!ledger) return <Shell>{null}</Shell>;

  const myId = ledger.members.find((m) => m.username === me)?.id;
  const isOwner = ledger.owner_id === myId;
  const name = (uid: number) => (uid === myId ? "You" : (ledger.members.find((m) => m.id === uid)?.username ?? "A former member"));
  const lower = (uid: number) => (uid === myId ? "you" : name(uid));
  const m = (amount: number) => money(amount, ledger.currency);
  const categoryName = (cid: number | null) => ledger.categories.find((c) => c.id === cid)?.name ?? "Uncategorized";
  const sameCurrency = wallets.filter((w) => w.currency === ledger.currency);
  const debtText = (d: Debt) => `${name(d.from_user_id)} ${d.from_user_id === myId ? "owe" : "owes"} ${lower(d.to_user_id)} ${m(d.amount)}`;

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto flex items-center gap-2 font-display text-3xl font-bold tracking-tight">
          <span className="h-3.5 w-3.5 rounded-full" style={{ background: slotColor(ledger.color_slot) }} />
          {ledger.name}
        </h1>
        <button className="btn btn-primary" onClick={() => setAdding(true)}>
          Add shared expense
        </button>
      </div>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}

      <div className="space-y-4">
        <Panel title="Who owes whom" note={`In ${ledger.currency}`}>
          {ledger.debts.length === 0 ? (
            <p className="text-sm text-ink-2">Everyone is settled up.</p>
          ) : (
            <ul className="divide-y divide-line">
              {ledger.debts.map((d) => {
                const open = settling?.debt === d;
                return (
                  <li key={`${d.from_user_id}-${d.to_user_id}`} className="py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="mr-auto font-medium">{debtText(d)}.</span>
                      {(d.from_user_id === myId || d.to_user_id === myId) && !open && (
                        <button
                          className="btn"
                          onClick={() => setSettling({ debt: d, amount: String(d.amount), date: iso(new Date()), wallet: "" })}
                        >
                          {d.from_user_id === myId ? "Settle up" : "Record a payment"}
                        </button>
                      )}
                    </div>
                    {open && settling && (
                      <form
                        className="mt-3 flex flex-wrap items-end gap-2"
                        onSubmit={async (e) => {
                          e.preventDefault();
                          const ok = await run(() =>
                            api(`/shared/${ledger.id}/settlements`, {
                              method: "POST",
                              json: {
                                from_user_id: d.from_user_id,
                                to_user_id: d.to_user_id,
                                amount: Number(settling.amount),
                                date: settling.date,
                                wallet_id: settling.wallet ? Number(settling.wallet) : null,
                              },
                            }),
                          );
                          if (ok) setSettling(null);
                        }}
                      >
                        <label className="text-sm font-medium">
                          Amount ({ledger.currency})
                          <input
                            className="field mt-1 block w-32 tnum"
                            type="number"
                            inputMode="decimal"
                            min="0.01"
                            step="0.01"
                            required
                            value={settling.amount}
                            onChange={(e) => setSettling({ ...settling, amount: e.target.value })}
                          />
                        </label>
                        <label className="text-sm font-medium">
                          Date
                          <input
                            className="field mt-1 block"
                            type="date"
                            required
                            value={settling.date}
                            onChange={(e) => setSettling({ ...settling, date: e.target.value })}
                          />
                        </label>
                        <label className="text-sm font-medium">
                          {d.from_user_id === myId ? "Paid from" : "Received in"}
                          <select
                            className="field mt-1 block"
                            value={settling.wallet}
                            onChange={(e) => setSettling({ ...settling, wallet: e.target.value })}
                          >
                            <option value="">Don&apos;t record in a wallet</option>
                            {sameCurrency.map((w) => (
                              <option key={w.id} value={w.id}>
                                {w.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button type="button" className="btn" onClick={() => setSettling(null)}>
                          Cancel
                        </button>
                        <button className="btn btn-primary">Save payment</button>
                      </form>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-3 text-xs text-ink-2">
            A payment recorded in a wallet moves its balance but doesn&apos;t count as spending or income.
          </p>
        </Panel>

        <Panel title="Expenses" note="The person who paid can edit or delete an expense">
          {ledger.expenses.length === 0 ? (
            <p className="py-4 text-center text-sm text-ink-2">No shared expenses yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {ledger.expenses.map((e) => (
                <li key={e.id} className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-baseline gap-x-3 py-3 text-sm sm:gap-x-4">
                  <span className="text-ink-2 tnum">{shortDate(e.date)}</span>
                  <span className="min-w-0">
                    <span className="block font-medium">{e.merchant || "No merchant"}</span>
                    <span className="block text-ink-2">
                      {e.splits.length ? e.splits.map((s) => categoryName(s.category_id)).join(", ") : categoryName(e.category_id)}. Paid by{" "}
                      {lower(e.paid_by)}.
                    </span>
                    <span className="block text-ink-2">{e.shares.map((s) => `${name(s.user_id)} ${s.percent}%`).join(", ")}</span>
                    {e.paid_by === myId && (
                      <span className="mt-1 flex gap-3 text-xs">
                        {confirmDelete === e.id ? (
                          <>
                            <button
                              className="font-medium text-critical"
                              onClick={() => run(() => api(`/transactions/${e.id}`, { method: "DELETE" })).then(() => setConfirmDelete(null))}
                            >
                              Delete expense
                            </button>
                            <button className="text-ink-2" onClick={() => setConfirmDelete(null)}>
                              Keep
                            </button>
                          </>
                        ) : (
                          <>
                            <button className="text-accent" onClick={() => api<Transaction>(`/transactions/${e.id}`).then(setEditing)}>
                              Edit
                            </button>
                            <button className="text-ink-2 hover:text-critical" onClick={() => setConfirmDelete(e.id)}>
                              Delete
                            </button>
                          </>
                        )}
                      </span>
                    )}
                  </span>
                  <span className="text-right tnum">
                    <span className="block font-medium">{m(e.amount_shared)}</span>
                    {e.currency !== ledger.currency && <span className="block text-xs text-ink-2">{money(e.amount, e.currency)}</span>}
                    {e.shares.some((s) => s.user_id === myId) && (
                      <span className="block text-xs text-ink-2">
                        Your share {m((e.amount_shared * e.shares.find((s) => s.user_id === myId)!.percent) / 100)}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {ledger.settlements.length > 0 && (
          <Panel title="Payments">
            <ul className="divide-y divide-line">
              {ledger.settlements.map((s) => {
                const party = s.from_user_id === myId || s.to_user_id === myId;
                const canRecord = party && myId !== undefined && !s.recorded_by.includes(myId);
                return (
                  <li key={s.id} className="py-3 text-sm">
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                      <span className="w-14 shrink-0 text-ink-2 tnum">{shortDate(s.date)}</span>
                      <span className="mr-auto">
                        {name(s.from_user_id)} paid {lower(s.to_user_id)} {m(s.amount)}.
                      </span>
                      {canRecord && recording?.id !== s.id && (
                        <button className="text-accent" onClick={() => setRecording({ id: s.id, wallet: String(sameCurrency[0]?.id ?? "") })}>
                          Record in my wallet
                        </button>
                      )}
                      {party && (
                        <button
                          className="text-ink-2 hover:text-critical"
                          title="Also removes it from any wallet it was recorded in"
                          onClick={() => run(() => api(`/shared/settlements/${s.id}`, { method: "DELETE" }))}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                    {recording?.id === s.id && (
                      <form
                        className="mt-2 flex flex-wrap items-end gap-2"
                        onSubmit={async (e) => {
                          e.preventDefault();
                          if (await run(() => api(`/shared/settlements/${s.id}/record`, { method: "POST", json: { wallet_id: Number(recording.wallet) } })))
                            setRecording(null);
                        }}
                      >
                        <label className="text-sm font-medium">
                          {s.from_user_id === myId ? "Paid from" : "Received in"}
                          <select
                            className="field mt-1 block"
                            required
                            value={recording.wallet}
                            onChange={(e) => setRecording({ ...recording, wallet: e.target.value })}
                          >
                            {sameCurrency.map((w) => (
                              <option key={w.id} value={w.id}>
                                {w.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button type="button" className="btn" onClick={() => setRecording(null)}>
                          Cancel
                        </button>
                        <button className="btn btn-primary" disabled={!sameCurrency.length}>
                          Record
                        </button>
                      </form>
                    )}
                  </li>
                );
              })}
            </ul>
          </Panel>
        )}

        <Panel title="Members">
          <ul className="flex flex-wrap gap-2 text-sm">
            {ledger.members.map((member) => (
              <li key={member.id} className="flex items-center gap-1.5 rounded-full bg-panel-sunk py-1 pr-1 pl-3">
                {member.id === myId ? `${member.username} (you)` : member.username}
                {member.id === ledger.owner_id && <span className="text-xs text-ink-2">owner</span>}
                {member.id !== ledger.owner_id && (isOwner || member.id === myId) && (
                  <button
                    aria-label={member.id === myId ? "Leave this shared wallet" : `Remove ${member.username}`}
                    title="Only once they're settled up"
                    className="rounded-full px-2 text-ink-2 hover:text-critical"
                    onClick={() =>
                      run(async () => {
                        await api(`/shared/${ledger.id}/members/${member.id}`, { method: "DELETE" });
                        if (member.id === myId) window.location.href = "/wallets/";
                      })
                    }
                  >
                    {member.id === myId ? "Leave" : "×"}
                  </button>
                )}
              </li>
            ))}
          </ul>
          {isOwner && (
            <form
              className="mt-4 flex flex-wrap gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (await run(() => api(`/shared/${ledger.id}/members`, { method: "POST", json: { username: newMember } }))) setNewMember("");
              }}
            >
              <input
                className="field min-w-0 flex-1 sm:max-w-64"
                aria-label="Username to add"
                placeholder="Their username"
                required
                value={newMember}
                onChange={(e) => setNewMember(e.target.value)}
              />
              <button className="btn btn-primary">Add person</button>
            </form>
          )}
          <p className="mt-3 text-xs text-ink-2">
            People added later share only the expenses added after they join. Expenses use {isOwner ? "your" : `${name(ledger.owner_id)}'s`}{" "}
            categories; in each person&apos;s own charts they count under the category with the same name, or &quot;Shared&quot;.
          </p>
          {isOwner && ledger.expenses.length === 0 && ledger.settlements.length === 0 && (
            <button
              className="mt-3 text-sm text-ink-2 hover:text-critical"
              onClick={() =>
                run(async () => {
                  await api(`/shared/${ledger.id}`, { method: "DELETE" });
                  window.location.href = "/wallets/";
                })
              }
            >
              Delete this shared wallet
            </button>
          )}
        </Panel>
      </div>

      {(adding || editing) && (
        <TransactionModal
          categories={categories}
          wallets={wallets}
          initial={editing ?? undefined}
          sharedWalletId={ledger.id}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
          onSaved={() => {
            setAdding(false);
            setEditing(null);
            load();
          }}
        />
      )}
    </Shell>
  );
}
