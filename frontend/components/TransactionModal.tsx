"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  Category,
  Frequency,
  Kind,
  Person,
  ReceiptScan,
  SharedExpense,
  SharedWallet,
  Transaction,
  equalShares,
  parseShares,
  TransactionInput,
  Wallet,
} from "@/lib/api";
import { currencySymbol, iso, money } from "@/lib/format";
import LocationField, { Location } from "@/components/LocationField";
import ReceivedField from "@/components/ReceivedField";
import Switch from "@/components/Switch";

const KINDS: { value: Kind; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

type SplitRow = { category_id: string; amount: string };

// Turning Shared on adds the "shared" tag, and turning it off takes it away.
const tagList = (tags: string) => tags.split(/[\s,]+/).map((t) => t.replace(/^#/, "")).filter(Boolean);
const withSharedTag = (tags: string, on: boolean) =>
  [...tagList(tags).filter((t) => t.toLowerCase() !== "shared"), ...(on ? ["shared"] : [])].join(", ");

export default function TransactionModal({
  categories,
  wallets,
  initial,
  sharedWalletId,
  onClose,
  onSaved,
}: {
  categories: Category[];
  wallets: Wallet[];
  initial?: Transaction;
  sharedWalletId?: number; // a new expense starts shared in this wallet
  onClose: () => void;
  onSaved: () => void;
}) {
  const [kind, setKind] = useState<Kind>(initial?.kind ?? "expense");
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [categoryId, setCategoryId] = useState(initial?.category_id ? String(initial.category_id) : "");
  const [walletId, setWalletId] = useState(String(initial?.wallet_id ?? wallets[0]?.id ?? ""));
  const [toWalletId, setToWalletId] = useState(initial?.to_wallet_id ? String(initial.to_wallet_id) : "");
  const [received, setReceived] = useState(initial?.to_amount ? String(initial.to_amount) : "");
  const [repeat, setRepeat] = useState<Frequency | "">("");
  const [hint, setHint] = useState("");
  const [location, setLocation] = useState<Location | null>(
    initial?.lat != null && initial?.lng != null ? { place: initial.place ?? "", lat: initial.lat, lng: initial.lng } : null,
  );
  const [locationSource, setLocationSource] = useState("");
  const [date, setDate] = useState(initial?.date ?? iso(new Date()));
  const [merchant, setMerchant] = useState(initial?.merchant ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [tags, setTags] = useState(initial?.tags ?? "");
  const [receiptPath, setReceiptPath] = useState(initial?.receipt_path ?? null);
  const [splits, setSplits] = useState<SplitRow[]>(
    initial?.splits.map((s) => ({ category_id: String(s.category_id), amount: String(s.amount) })) ?? [],
  );
  const [showDetails, setShowDetails] = useState(
    Boolean(initial && (initial.notes || initial.tags || initial.splits.length || initial.lat != null)),
  );
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const cameraInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // A shared expense is either in a shared wallet, or shared directly with people you pick.
  const [shared, setShared] = useState(Boolean(initial?.shared_members || sharedWalletId));
  const [ledgers, setLedgers] = useState<SharedWallet[] | null>(null);
  const [sharedId, setSharedId] = useState(String(initial?.shared_wallet_id ?? sharedWalletId ?? ""));
  const [me, setMe] = useState<Person | null>(null);
  const [people, setPeople] = useState<Person[]>([]); // shared directly, besides you
  const [person, setPerson] = useState("");
  const [personError, setPersonError] = useState("");
  const ledger = kind === "expense" && shared ? ledgers?.find((l) => String(l.id) === sharedId) : undefined;
  // An expense in a shared wallet you left stays in it; the others' balances still count it.
  const left = ledgers !== null && kind === "expense" && shared && !!sharedId && !ledger;
  const direct = kind === "expense" && shared && !sharedId;
  const members: Person[] = ledger ? ledger.members : direct && me ? [{ id: me.id, username: "You" }, ...people] : [];
  // Percent per person; an edited expense starts from its saved split.
  const [percents, setPercents] = useState<Record<number, string>>(() =>
    Object.fromEntries(Object.entries(parseShares(initial?.shared_members ?? null)).map(([id, p]) => [id, String(p)])),
  );
  const splitEqually = (list: Person[]) =>
    setPercents(Object.fromEntries(Object.entries(equalShares(list.map((m) => m.id))).map(([id, p]) => [id, String(p)])));
  useEffect(() => {
    if (ledger && Object.keys(percents).length === 0) splitEqually(ledger.members);
  }, [ledger, percents]);
  const percentTotal = Object.values(percents).reduce((sum, p) => sum + (Number(p) || 0), 0);
  const shareMismatch = members.length > 1 && Math.abs(percentTotal - 100) > 0.01;
  const needsPeople = direct && people.length === 0;

  useEffect(() => {
    api<SharedWallet[]>("/shared").then(setLedgers);
    api<Person>("/auth/me").then(setMe);
    if (initial?.shared_members && !initial.shared_wallet_id) {
      api<SharedExpense>(`/shared-expenses/${initial.id}`).then((e) =>
        setPeople(e.shares.filter((s) => s.user_id !== e.paid_by.id).map((s) => ({ id: s.user_id, username: s.username }))),
      );
    }
  }, [initial]);

  function toggleShared(on: boolean) {
    setShared(on);
    setTags(withSharedTag(tags, on));
    if (sharedId) {
      setSharedId("");
      setCategoryId("");
      setSplits([]);
    }
    setPeople([]);
    setPercents({});
    setPersonError("");
  }

  function choosePeople(next: Person[]) {
    setPeople(next);
    if (me && next.length) splitEqually([me, ...next]);
    else setPercents({});
  }

  async function addPerson() {
    const name = person.trim();
    if (!name) return;
    setPersonError("");
    try {
      const found = await api<Person>(`/auth/users/${encodeURIComponent(name)}`);
      if (found.id === me?.id) return setPersonError("That's you. You're already in.");
      if (!people.some((p) => p.id === found.id)) choosePeople([...people, found]);
      setPerson("");
    } catch (err) {
      setPersonError(err instanceof ApiError ? err.message : "Couldn't look them up. Check that TracepAI is running.");
    }
  }

  // A shared expense uses the shared wallet owner's categories.
  const options = (kind === "expense" && ledger ? ledger.categories : categories).filter((c) => c.kind === kind);
  const isTransfer = kind === "transfer";
  const currencyOf = (id: string) => wallets.find((w) => String(w.id) === id)?.currency;
  const currency = currencyOf(walletId) ?? "USD";
  const crossCurrency = isTransfer && !!toWalletId && currencyOf(toWalletId) !== currency;

  async function suggestCategory(name: string, forKind: Kind = kind, current = categoryId) {
    if (forKind === "transfer" || current || splits.length || sharedId || !name.trim()) return;
    const params = new URLSearchParams({ merchant: name, kind: forKind });
    const suggestion = await api<{ category_id: number; source: string } | null>(`/categories/suggest?${params}`);
    if (suggestion) {
      setCategoryId(String(suggestion.category_id));
      setHint(suggestion.source === "history" ? "Category from your past transactions" : "Category guessed from the name");
    }
  }
  const splitTotal = splits.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const splitMismatch = splits.length > 0 && Math.abs(splitTotal - Number(amount)) > 0.005;

  async function scanReceipt(file: File) {
    setBusy(true);
    setScanning(true);
    setError("");
    setStatus("");
    const form = new FormData();
    form.append("file", file);
    try {
      const scan = await api<ReceiptScan>("/receipts/scan", { method: "POST", body: form });
      setReceiptPath(scan.receipt_path);
      if (scan.amount) setAmount(String(scan.amount));
      if (scan.date) setDate(scan.date);
      if (scan.merchant) {
        setMerchant(scan.merchant);
        setCategoryId("");
        suggestCategory(scan.merchant, "expense", "");
      }
      if (scan.lat != null && scan.lng != null) {
        const { lat, lng } = scan;
        const place = await api<{ name: string }>(`/places/reverse?lat=${lat}&lng=${lng}`).catch(() => ({ name: "" }));
        setLocation({ place: place.name || "Photo location", lat, lng });
        setLocationSource("Location from the photo");
        setShowDetails(true);
      }
      setStatus(scan.amount ? "Read. Check the details before saving." : "Attached, but no total was found. Enter the amount yourself.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The document could not be read. Try a sharper photo.");
    } finally {
      setBusy(false);
      setScanning(false);
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body: TransactionInput = {
      date,
      amount: Number(amount),
      kind,
      merchant,
      wallet_id: Number(walletId),
      to_wallet_id: isTransfer ? Number(toWalletId) : null,
      to_amount: crossCurrency ? Number(received) : null,
      category_id: isTransfer || splits.length ? null : categoryId ? Number(categoryId) : null,
      notes,
      tags: tags
        .split(/[\s,]+/)
        .map((t) => t.replace(/^#/, ""))
        .filter(Boolean)
        .join(","),
      receipt_path: receiptPath,
      place: isTransfer ? null : (location?.place ?? null),
      lat: isTransfer ? null : (location?.lat ?? null),
      lng: isTransfer ? null : (location?.lng ?? null),
      splits: isTransfer ? [] : splits.map((s) => ({ category_id: Number(s.category_id), amount: Number(s.amount) })),
      repeat: repeat || null,
      goal_id: initial?.goal_id ?? null,
      shared_wallet_id: kind === "expense" && shared && sharedId ? Number(sharedId) : null, // also a shared wallet you left
      shares: ledger || direct ? Object.fromEntries(Object.entries(percents).map(([id, p]) => [id, Number(p) || 0])) : null,
    };
    try {
      await api(initial ? `/transactions/${initial.id}` : "/transactions", {
        method: initial ? "PUT" : "POST",
        json: body,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saving failed. Check that TracepAI is running.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="txn-title"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-panel p-6 sm:max-w-md sm:rounded-3xl"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 id="txn-title" className="font-display text-xl font-semibold">
            {initial ? "Edit transaction" : "Add transaction"}
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-ink-2 hover:text-ink">
            Cancel
          </button>
        </div>

        <div className="mb-4 grid grid-cols-3 rounded-full bg-panel-sunk p-1 text-sm font-medium">
          {KINDS.map((k) => (
            <button
              key={k.value}
              type="button"
              aria-pressed={kind === k.value}
              onClick={() => {
                setKind(k.value);
                setCategoryId("");
                setSplits([]);
                setHint("");
              }}
              className={`rounded-full py-1.5 ${kind === k.value ? "bg-panel shadow-sm" : "text-ink-2"}`}
            >
              {k.label}
            </button>
          ))}
        </div>

        <label className="block text-sm font-medium">
          Amount{currency !== "USD" && ` (${currency})`}
          <div className="mt-1.5 flex items-center gap-2 border-b-2 border-accent pb-1">
            <span className="font-display text-3xl text-ink-2">{currencySymbol(currency)}</span>
            <input
              className="w-full bg-transparent font-display text-4xl font-semibold tnum outline-none"
              inputMode="decimal"
              type="number"
              step="0.01"
              min="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              autoFocus
              placeholder="0.00"
            />
          </div>
        </label>

        <div className="mt-4 grid grid-cols-2 gap-3">
          {isTransfer ? (
            <label className="block text-sm font-medium">
              To
              <select className="field mt-1.5" value={toWalletId} onChange={(e) => setToWalletId(e.target.value)} required>
                <option value="">Choose</option>
                {wallets
                  .filter((w) => String(w.id) !== walletId)
                  .map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
              </select>
            </label>
          ) : (
            <label className="block text-sm font-medium">
              Category
              <select
                className="field mt-1.5"
                value={categoryId}
                onChange={(e) => {
                  setCategoryId(e.target.value);
                  setHint("");
                }}
                disabled={splits.length > 0}
              >
                <option value="">{splits.length ? "Split" : "Uncategorized"}</option>
                {options.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="block text-sm font-medium">
            {isTransfer ? "From" : kind === "income" ? "Into" : "Paid with"}
            <select className="field mt-1.5" value={walletId} onChange={(e) => setWalletId(e.target.value)} required>
              {wallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
          {crossCurrency && (
            <div className="col-span-2">
              <ReceivedField amount={amount} from={currency} to={currencyOf(toWalletId)} date={date} value={received} onChange={setReceived} />
            </div>
          )}
          {kind === "expense" && (
            <div className="col-span-2 flex items-center gap-3">
              <Switch checked={shared} onChange={toggleShared} labelledBy="txn-shared" />
              <span id="txn-shared" className="text-sm font-medium">
                Shared
              </span>
              <span className="text-xs text-ink-2">
                {shared ? "The whole amount comes out of your wallet; only your share counts as your spending." : "Only yours."}
              </span>
            </div>
          )}
          {left && (
            <p className="col-span-2 text-sm text-ink-2">
              You left the shared wallet this expense is in, so only its merchant, notes, tags and place can change.
            </p>
          )}
          {kind === "expense" && shared && !left && ledgers && ledgers.length > 0 && (
            <label className="col-span-2 block text-sm font-medium">
              Shared in
              <select
                className="field mt-1.5"
                value={sharedId}
                onChange={(e) => {
                  setSharedId(e.target.value);
                  setCategoryId("");
                  setSplits([]);
                  setPeople([]);
                  setPercents({});
                }}
              >
                <option value="">Just this expense, with people I choose</option>
                {ledgers.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(ledger || direct) && (
            <fieldset className="col-span-2 rounded-xl border border-line p-3 text-sm">
              <legend className="px-1 font-medium">{direct ? "People and their share" : "Share of each person"}</legend>
              <ul className="space-y-2">
                {members.map((m) => (
                  <li key={m.id} className="flex items-center gap-2">
                    <span className="mr-auto">{m.username}</span>
                    <span className="text-ink-2 tnum">{money(((Number(amount) || 0) * (Number(percents[m.id]) || 0)) / 100, currency)}</span>
                    <label className="flex items-center gap-1">
                      <input
                        className="field w-20 py-1 text-right tnum"
                        type="number"
                        inputMode="decimal"
                        min="0"
                        max="100"
                        step="0.01"
                        aria-label={`${m.username === "You" ? "Your" : `${m.username}'s`} share in percent`}
                        value={percents[m.id] ?? ""}
                        onChange={(e) => setPercents({ ...percents, [m.id]: e.target.value })}
                      />
                      <span className="text-ink-2">%</span>
                    </label>
                    {direct &&
                      (m.id === me?.id ? (
                        <span className="w-6" />
                      ) : (
                        <button
                          type="button"
                          aria-label={`Remove ${m.username}`}
                          className="w-6 text-ink-2 hover:text-critical"
                          onClick={() => choosePeople(people.filter((p) => p.id !== m.id))}
                        >
                          &times;
                        </button>
                      ))}
                  </li>
                ))}
              </ul>
              {direct && (
                <div className="mt-3">
                  <div className="flex gap-2">
                    <input
                      className="field py-1.5"
                      aria-label="Share with, by username"
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
                  <p className={`mt-1 text-xs ${personError ? "text-critical" : "text-ink-2"}`} role={personError ? "alert" : undefined}>
                    {personError || (needsPeople ? "Add someone to share it with. They need a TracepAI account." : "They see their share and can mark it paid back.")}
                  </p>
                </div>
              )}
              {members.length > 1 && (
                <div className="mt-2 flex items-center gap-3 text-xs">
                  <span className={shareMismatch ? "text-critical" : "text-ink-2"} aria-live="polite">
                    {shareMismatch
                      ? `${Math.round(percentTotal * 100) / 100}% so far; ${Math.abs(Math.round((100 - percentTotal) * 100) / 100)}% ${percentTotal > 100 ? "too much" : "left"}`
                      : "Adds up to 100%"}
                  </span>
                  <button type="button" className="ml-auto text-accent" onClick={() => splitEqually(members)}>
                    Split equally
                  </button>
                </div>
              )}
            </fieldset>
          )}
          {hint && <p className="col-span-2 -mt-1 text-xs text-ink-2">{hint}</p>}
          <label className="block text-sm font-medium">
            Date
            <input className="field mt-1.5" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="block text-sm font-medium">
            {kind === "expense" ? "Merchant" : kind === "income" ? "From" : "Description"}
            <input
              className="field mt-1.5"
              value={merchant}
              onChange={(e) => setMerchant(e.target.value)}
              onBlur={(e) => suggestCategory(e.target.value)}
            />
          </label>
        </div>

        {kind === "expense" && (
          <div className="mt-4">
            <input
              ref={cameraInput}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && scanReceipt(e.target.files[0])}
            />
            <input
              ref={fileInput}
              type="file"
              accept="image/*,application/pdf"
              className="hidden"
              aria-label="Upload a receipt, ticket or invoice"
              onChange={(e) => e.target.files?.[0] && scanReceipt(e.target.files[0])}
            />
            <div className="grid grid-cols-2 gap-2">
              <button type="button" className="btn" onClick={() => cameraInput.current?.click()} disabled={busy}>
                Take photo
              </button>
              <button type="button" className="btn" onClick={() => fileInput.current?.click()} disabled={busy}>
                Upload file
              </button>
            </div>
            {scanning && (
              <p role="status" className="mt-3 flex items-center gap-2 text-sm text-ink-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-accent motion-reduce:animate-none" />
                Reading the receipt
              </p>
            )}
            {receiptPath && (
              <a
                href={`/api/receipts/${receiptPath}`}
                target="_blank"
                rel="noreferrer"
                className="mt-2 block text-center text-sm text-accent underline"
              >
                View attached receipt
              </a>
            )}
          </div>
        )}
        {status && (
          <p role="status" className="mt-3 text-sm text-ink-2">
            {status}
          </p>
        )}

        <button
          type="button"
          className="mt-5 text-sm font-medium text-accent"
          aria-expanded={showDetails}
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? "Hide notes, tags and more" : "Add place, notes, tags, splits or repeat"}
        </button>

        {showDetails && (
          <div className="mt-3 space-y-3">
            {!isTransfer && (
              <LocationField
                value={location}
                source={locationSource}
                onChange={(l) => {
                  setLocation(l);
                  setLocationSource("");
                }}
              />
            )}
            <label className="block text-sm font-medium">
              Notes
              <textarea className="field mt-1.5" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              Tags
              <input
                className="field mt-1.5"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="vacation, workReimbursable"
              />
            </label>
            {!initial && (
              <label className="block text-sm font-medium">
                Repeat
                <select className="field mt-1.5" value={repeat} onChange={(e) => setRepeat(e.target.value as Frequency | "")}>
                  <option value="">Never</option>
                  <option value="weekly">Every week</option>
                  <option value="monthly">Every month</option>
                  <option value="yearly">Every year</option>
                </select>
              </label>
            )}
            {kind === "expense" && (
              <fieldset>
                <legend className="text-sm font-medium">Split across categories</legend>
                {splits.map((s, i) => (
                  <div key={i} className="mt-2 flex gap-2">
                    <select
                      className="field"
                      aria-label={`Split ${i + 1} category`}
                      value={s.category_id}
                      required
                      onChange={(e) => setSplits(splits.map((r, j) => (j === i ? { ...r, category_id: e.target.value } : r)))}
                    >
                      <option value="">Choose</option>
                      {options.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <input
                      className="field w-28 tnum"
                      aria-label={`Split ${i + 1} amount`}
                      type="number"
                      step="0.01"
                      min="0.01"
                      required
                      value={s.amount}
                      onChange={(e) => setSplits(splits.map((r, j) => (j === i ? { ...r, amount: e.target.value } : r)))}
                    />
                    <button
                      type="button"
                      aria-label={`Remove split ${i + 1}`}
                      className="px-2 text-ink-2 hover:text-critical"
                      onClick={() => setSplits(splits.filter((_, j) => j !== i))}
                    >
                      &times;
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="mt-2 text-sm text-accent"
                  onClick={() =>
                    setSplits([
                      ...splits,
                      { category_id: splits.length ? "" : categoryId, amount: splits.length ? "" : amount },
                    ])
                  }
                >
                  Add a split
                </button>
                {splitMismatch && (
                  <p className="mt-1 text-sm text-critical">
                    Splits add up to {money(splitTotal, currency)}. They need to match the amount, {money(Number(amount) || 0, currency)}.
                  </p>
                )}
              </fieldset>
            )}
          </div>
        )}

        {error && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {error}
          </p>
        )}
        <button className="btn btn-primary mt-6 w-full py-2.5" disabled={busy || splitMismatch || shareMismatch || needsPeople}>
          {initial ? "Save changes" : "Add transaction"}
        </button>
      </form>
    </div>
  );
}
