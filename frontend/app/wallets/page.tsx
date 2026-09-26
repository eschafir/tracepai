"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import Shell from "@/components/Shell";
import { api, ApiError, SharedWallet, Wallet, WalletKind } from "@/lib/api";
import { money, slotColor } from "@/lib/format";

const KINDS: { value: WalletKind; label: string }[] = [
  { value: "bank", label: "Bank account" },
  { value: "card", label: "Credit card" },
  { value: "cash", label: "Cash" },
  { value: "savings", label: "Savings" },
];

// A shared wallet has no type or starting balance (money stays in each person's own wallets), but it has people.
type Draft = { name: string; kind: WalletKind; color_slot: number; opening_balance: string; currency: string; members: string[] };

const currencyName = new Intl.DisplayNames(["en"], { type: "currency" });

const empty: Draft = { name: "", kind: "bank", color_slot: 1, opening_balance: "0", currency: "USD", members: [] };

function WalletForm({ initial, initialShared, canToggle, currencies, currencyLocked, submitLabel, onSubmit, onCancel }: {
  initial: Draft;
  initialShared: boolean;
  canToggle: boolean; // only when adding: a normal wallet can't become shared, or the other way round
  currencies: string[];
  currencyLocked?: boolean;
  submitLabel: string;
  onSubmit: (draft: Draft, shared: boolean) => Promise<void>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [shared, setShared] = useState(initialShared);
  const [person, setPerson] = useState("");
  const id = useId(); // the add form and an edit form can be open at once

  function addPerson() {
    const name = person.trim();
    if (name && !draft.members.includes(name)) setDraft({ ...draft, members: [...draft.members, name] });
    setPerson("");
  }

  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto]"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit(draft, shared);
      }}
    >
      <div className="flex items-center gap-3 sm:col-span-4">
        <button
          type="button"
          role="switch"
          aria-checked={shared}
          aria-labelledby={`${id}-shared`}
          disabled={!canToggle}
          onClick={() => setShared(!shared)}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
            shared ? "bg-accent" : "bg-panel-sunk ring-1 ring-line"
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${shared ? "translate-x-5" : ""}`}
          />
        </button>
        <span id={`${id}-shared`} className="text-sm font-medium">
          Shared
        </span>
        <span className="text-sm text-ink-2">
          {shared ? "Split expenses with other people. Each person pays from their own wallets." : "Only you use it."}
        </span>
      </div>
      <label className={`text-sm font-medium ${shared ? "sm:col-span-2" : ""}`}>
        Name
        <input
          className="field mt-1"
          required
          placeholder={shared ? "Home, Trip to Bariloche" : ""}
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </label>
      {!shared && (
        <label className="text-sm font-medium">
          Type
          <select className="field mt-1" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as WalletKind })}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className={`text-sm font-medium ${shared ? "sm:col-span-2" : ""}`}>
        Currency
        <select
          className="field mt-1 block disabled:cursor-not-allowed disabled:opacity-60 sm:w-56"
          required
          disabled={currencyLocked}
          aria-describedby={currencyLocked ? `${id}-locked` : undefined}
          value={draft.currency}
          onChange={(e) => setDraft({ ...draft, currency: e.target.value })}
        >
          {(currencies.includes(draft.currency) ? currencies : [draft.currency, ...currencies]).map((c) => (
            <option key={c} value={c}>
              {c} - {currencyName.of(c)}
            </option>
          ))}
        </select>
      </label>
      {!shared && (
        <label className="text-sm font-medium">
          Starting balance
          <input
            className="field mt-1 block tnum sm:w-36"
            type="number"
            step="0.01"
            required
            value={draft.opening_balance}
            onChange={(e) => setDraft({ ...draft, opening_balance: e.target.value })}
          />
        </label>
      )}
      {currencyLocked && (
        <p id={`${id}-locked`} className="-mt-1 text-xs text-ink-2 sm:col-span-4">
          {shared ? "This shared wallet has expenses" : "This wallet has transactions"}, so its currency can&apos;t change.
        </p>
      )}
      {shared && (
        <div className="sm:col-span-4">
          <label className="text-sm font-medium" htmlFor={`${id}-person`}>
            People
          </label>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {draft.members.map((name) => (
              <span key={name} className="flex items-center gap-1 rounded-full bg-panel-sunk py-1 pr-1 pl-3 text-sm">
                {name}
                <button
                  type="button"
                  aria-label={`Remove ${name}`}
                  className="rounded-full px-2 text-ink-2 hover:text-critical"
                  onClick={() => setDraft({ ...draft, members: draft.members.filter((m) => m !== name) })}
                >
                  &times;
                </button>
              </span>
            ))}
            <input
              id={`${id}-person`}
              className="field w-48 py-1.5"
              placeholder="Their username"
              value={person}
              onChange={(e) => setPerson(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addPerson();
                }
              }}
            />
            <button type="button" className="btn" onClick={addPerson} disabled={!person.trim()}>
              Add
            </button>
          </div>
          <p className="mt-1 text-xs text-ink-2">
            They need to have signed up. People can be removed once they&apos;re settled up.
          </p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-4">
        <fieldset className="flex gap-1" aria-label="Color">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((slot) => (
            <button
              key={slot}
              type="button"
              aria-label={`Color ${slot}`}
              aria-pressed={draft.color_slot === slot}
              onClick={() => setDraft({ ...draft, color_slot: slot })}
              className={`h-6 w-6 rounded-full ${draft.color_slot === slot ? "ring-2 ring-ink ring-offset-2 ring-offset-panel" : ""}`}
              style={{ background: slotColor(slot) }}
            />
          ))}
        </fieldset>
        <span className="ml-auto flex gap-2">
          {onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          )}
          <button className="btn btn-primary">{submitLabel}</button>
        </span>
      </div>
    </form>
  );
}

function owedText(s: SharedWallet) {
  if (s.my_balance > 0) return { text: `You're owed ${money(s.my_balance, s.currency)}`, tone: "text-up" };
  if (s.my_balance < 0) return { text: `You owe ${money(-s.my_balance, s.currency)}`, tone: "text-critical" };
  return { text: "Settled up", tone: "text-ink-2" };
}

export default function WalletsPage() {
  const [wallets, setWallets] = useState<Wallet[] | null>(null);
  const [shared, setShared] = useState<SharedWallet[]>([]);
  const [myId, setMyId] = useState<number | null>(null);
  const [currencies, setCurrencies] = useState<string[]>([]);
  const [editing, setEditing] = useState<string | null>(null); // "w3" for a wallet, "s2" for a shared wallet
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [w, s, me] = await Promise.all([api<Wallet[]>("/wallets"), api<SharedWallet[]>("/shared"), api<{ id: number }>("/auth/me")]);
    setWallets(w);
    setShared(s);
    setMyId(me.id);
  }, []);

  useEffect(() => {
    load();
    api<string[]>("/fx/currencies").then(setCurrencies);
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      setEditing(null);
      setConfirmDelete(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change was not saved. Check that TracepAI is running.");
    }
  }

  const walletBody = (d: Draft) => ({
    name: d.name,
    kind: d.kind,
    color_slot: d.color_slot,
    currency: d.currency,
    opening_balance: Number(d.opening_balance),
  });
  const sharedBody = (d: Draft) => ({ name: d.name, color_slot: d.color_slot, currency: d.currency, members: d.members });
  const total = wallets?.reduce((s, w) => s + w.balance_usd, 0) ?? 0;

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-3xl font-bold tracking-tight">Wallets</h1>
        {wallets && <p className="text-ink-2">Total {money(total)}</p>}
      </div>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}
      {wallets && (
        <ul className="mb-4 divide-y divide-line rounded-2xl bg-panel">
          {wallets.map((w) =>
            editing === `w${w.id}` ? (
              <li key={`w${w.id}`} className="p-5">
                <WalletForm
                  initial={{ ...w, opening_balance: String(w.opening_balance), members: [] }}
                  initialShared={false}
                  canToggle={false}
                  currencies={currencies}
                  currencyLocked={w.in_use}
                  submitLabel="Save changes"
                  onCancel={() => setEditing(null)}
                  onSubmit={(d) => run(() => api(`/wallets/${w.id}`, { method: "PUT", json: walletBody(d) }))}
                />
              </li>
            ) : (
              <li
                key={`w${w.id}`}
                className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-5 py-4 sm:grid-cols-[auto_1fr_auto_auto] sm:gap-x-5"
              >
                <span className="h-3 w-3 rounded-full" style={{ background: slotColor(w.color_slot) }} />
                <Link href={`/transactions/?wallet=${w.id}`} className="hover:underline">
                  <span className="block font-medium">{w.name}</span>
                  <span className="block text-sm text-ink-2">{KINDS.find((k) => k.value === w.kind)?.label}</span>
                </Link>
                <span className="text-right">
                  <span className={`block font-display text-xl font-semibold tnum ${w.balance < 0 ? "text-critical" : ""}`}>
                    {money(w.balance, w.currency)}
                  </span>
                  {w.currency !== "USD" && <span className="block text-sm text-ink-2 tnum">{money(w.balance_usd)}</span>}
                </span>
                <span className="col-start-2 flex gap-3 text-sm sm:col-start-auto">
                  <button className="text-accent" onClick={() => setEditing(`w${w.id}`)}>
                    Edit
                  </button>
                  <button className="text-ink-2 hover:text-critical" onClick={() => run(() => api(`/wallets/${w.id}`, { method: "DELETE" }))}>
                    Delete
                  </button>
                </span>
              </li>
            ),
          )}
          {shared.map((s) => {
            const owner = s.owner_id === myId;
            const others = s.members.filter((m) => m.id !== myId).map((m) => m.username);
            const owed = owedText(s);
            if (editing === `s${s.id}`) {
              return (
                <li key={`s${s.id}`} className="p-5">
                  <WalletForm
                    initial={{
                      ...empty,
                      name: s.name,
                      color_slot: s.color_slot,
                      currency: s.currency,
                      members: s.members.filter((m) => m.id !== s.owner_id).map((m) => m.username),
                    }}
                    initialShared
                    canToggle={false}
                    currencies={currencies}
                    currencyLocked={s.in_use}
                    submitLabel="Save changes"
                    onCancel={() => setEditing(null)}
                    onSubmit={(d) => run(() => api(`/shared/${s.id}`, { method: "PUT", json: sharedBody(d) }))}
                  />
                </li>
              );
            }
            return (
              <li
                key={`s${s.id}`}
                className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-5 py-4 sm:grid-cols-[auto_1fr_auto_auto] sm:gap-x-5"
              >
                <span className="h-3 w-3 rounded-full" style={{ background: slotColor(s.color_slot) }} />
                <Link href={`/shared/?id=${s.id}`} className="hover:underline">
                  <span className="block font-medium">{s.name}</span>
                  <span className="block text-sm text-ink-2">
                    {others.length ? `Shared with ${others.join(", ")}` : "Shared, no one added yet"}
                  </span>
                </Link>
                <span className={`text-right text-sm font-medium tnum ${owed.tone}`}>{owed.text}</span>
                <span className="col-start-2 flex flex-wrap gap-3 text-sm sm:col-start-auto">
                  {owner && confirmDelete === s.id ? (
                    <>
                      <span className="w-full text-ink-2 sm:w-auto">
                        Delete {s.name} and its {s.expense_count} {s.expense_count === 1 ? "expense" : "expenses"}? They are removed from
                        everyone&apos;s wallets.
                      </span>
                      <button className="font-medium text-critical" onClick={() => run(() => api(`/shared/${s.id}`, { method: "DELETE" }))}>
                        Delete
                      </button>
                      <button className="text-ink-2" onClick={() => setConfirmDelete(null)}>
                        Keep
                      </button>
                    </>
                  ) : owner ? (
                    <>
                      <button className="text-accent" onClick={() => setEditing(`s${s.id}`)}>
                        Edit
                      </button>
                      <button className="text-ink-2 hover:text-critical" onClick={() => setConfirmDelete(s.id)}>
                        Delete
                      </button>
                    </>
                  ) : (
                    <Link className="text-accent" href={`/shared/?id=${s.id}`}>
                      Open
                    </Link>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <section className="rounded-2xl bg-panel p-5">
        <h2 className="mb-4 font-display text-lg font-semibold">Add a wallet</h2>
        <WalletForm
          key={`${wallets?.length}-${shared.length}`}
          initial={empty}
          initialShared={false}
          canToggle
          currencies={currencies}
          submitLabel="Add wallet"
          onSubmit={(d, isShared) =>
            run(() =>
              isShared
                ? api("/shared", { method: "POST", json: sharedBody(d) })
                : api("/wallets", { method: "POST", json: walletBody(d) }),
            )
          }
        />
      </section>
    </Shell>
  );
}
