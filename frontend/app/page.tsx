"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import TransactionModal from "@/components/TransactionModal";
import {
  BalanceChart,
  Empty,
  NetWorthChart,
  NetWorthPoint,
  BalancePoint,
  BudgetBars,
  BudgetStatus,
  CashflowChart,
  CashflowPoint,
  CategoryDonut,
  CategoryTotal,
  ComparisonChart,
  ComparisonPoint,
  Panel,
  RankedBars,
} from "@/components/charts";
import MonthSummary from "@/components/MonthSummary";
import { GoalsPanel } from "@/components/goals";
import SortablePanels from "@/components/SortablePanels";
import { api, BudgetPlan, BudgetStyle, Category, Goal, PriceChange, Settings, Upcoming, Wallet } from "@/lib/api";
import { Alerts, GroupBars, ZeroBasedSummary } from "@/components/budgetViews";
import { money, Period, periodRange, shortDate, slotColor } from "@/lib/format";

type Merchants = {
  largest: { id: number; date: string; merchant: string; amount: number }[];
  frequent: { merchant: string; count: number; total: number }[];
};

type Data = {
  balance: BalancePoint[];
  networth: NetWorthPoint[];
  categories: CategoryTotal[];
  cashflow: CashflowPoint[];
  budgets: BudgetStatus[];
  merchants: Merchants;
  comparison: ComparisonPoint[];
  wallets: Wallet[];
  upcoming: Upcoming[];
  goals: Goal[];
  prices: PriceChange[];
  plan: BudgetPlan;
  style: BudgetStyle;
};

const PERIODS: { value: Period; label: string }[] = [
  { value: "week", label: "7 days" },
  { value: "month", label: "This month" },
  { value: "year", label: "This year" },
];

export default function Dashboard() {
  const [period, setPeriod] = useState<Period>("month");
  const [data, setData] = useState<Data | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [wallet, setWallet] = useState("");
  const [adding, setAdding] = useState(false);
  const [layout, setLayout] = useState<string[]>([]);
  const bucket = period === "year" ? "month" : "day";

  const load = useCallback(async () => {
    const scope = wallet ? `wallet=${wallet}` : "";
    const range = new URLSearchParams({ ...periodRange(period), ...(wallet && { wallet }) });
    const [balance, cats, cashflow, budgets, merchants, comparison, categoryList, wallets, upcoming, goals, networth, prices, plan, settings] = await Promise.all([
      api<BalancePoint[]>(`/analytics/balance?${scope}`),
      api<CategoryTotal[]>(`/analytics/categories?${range}`),
      api<CashflowPoint[]>(`/analytics/cashflow?${range}&bucket=${bucket}`),
      api<BudgetStatus[]>("/analytics/budgets"),
      api<Merchants>(`/analytics/merchants?${range}&limit=6`),
      api<ComparisonPoint[]>(`/analytics/comparison?${scope}`),
      api<Category[]>("/categories"),
      api<Wallet[]>("/wallets"),
      api<Upcoming[]>("/recurring/upcoming?days=14"),
      api<Goal[]>("/goals"),
      api<NetWorthPoint[]>("/analytics/networth"),
      api<PriceChange[]>("/recurring/price-changes"),
      api<BudgetPlan>("/analytics/budget-plan"),
      api<Settings>("/settings"),
    ]);
    setData({ balance, categories: cats, cashflow, budgets, merchants, comparison, wallets, upcoming, goals, networth, prices, plan, style: settings.budget_style });
    setCategories(categoryList);
    setLayout(settings.overview_layout);
  }, [period, bucket, wallet]);

  useEffect(() => {
    load();
  }, [load]);

  const income = data?.cashflow.reduce((s, p) => s + p.income, 0) ?? 0;
  const spent = data?.cashflow.reduce((s, p) => s + p.expense, 0) ?? 0;
  const current = data?.balance.at(-1)?.balance ?? 0;
  const periodLabel = PERIODS.find((p) => p.value === period)!.label.toLowerCase();
  const selected = data?.wallets.find((w) => String(w.id) === wallet);
  const walletName = (id: number | null) => data?.wallets.find((w) => w.id === id)?.name ?? "";

  const today = new Date().getDate();
  const pace = data?.comparison[today - 1];
  const paceDelta = pace?.current != null && pace.previous != null ? pace.current - pace.previous : null;

  return (
    <Shell
      actions={
        <button className="btn btn-primary" onClick={() => setAdding(true)}>
          Add transaction
        </button>
      }
    >
      {data && (
        <div className="space-y-4">
          <Alerts budgets={data.budgets} prices={data.prices} wallets={data.wallets} />
          <section className="rounded-2xl bg-panel p-5 sm:p-7">
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div>
                <p className="text-sm text-ink-2">{selected ? `In ${selected.name}${selected.currency !== "USD" ? ", in USD" : ""}` : "Money on hand"}</p>
                <p className="font-display text-5xl font-bold tracking-tight tnum sm:text-7xl">{money(current)}</p>
              </div>
              <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                <div>
                  <dt className="text-ink-2">In, {periodLabel}</dt>
                  <dd className="font-display text-xl font-semibold tnum">{money(income)}</dd>
                </div>
                <div>
                  <dt className="text-ink-2">Out, {periodLabel}</dt>
                  <dd className="font-display text-xl font-semibold tnum">{money(spent)}</dd>
                </div>
                <div>
                  <dt className="text-ink-2">Net</dt>
                  <dd className={`font-display text-xl font-semibold tnum ${income - spent >= 0 ? "text-up" : "text-critical"}`}>
                    {income - spent >= 0 ? "+" : "−"}
                    {money(Math.abs(income - spent))}
                  </dd>
                </div>
              </dl>
            </div>
            <div className="mt-6">
              <BalanceChart data={data.balance} />
            </div>
            <div role="radiogroup" aria-label="Wallet" className="mt-5 flex flex-wrap gap-2">
              {[
                { id: "", name: "All wallets", color_slot: null, balance: data.wallets.reduce((s, w) => s + w.balance_usd, 0), currency: "USD" },
                ...data.wallets,
              ].map(
                (w) => {
                  const active = String(w.id) === wallet;
                  return (
                    <button
                      key={w.id}
                      role="radio"
                      aria-checked={active}
                      onClick={() => setWallet(String(w.id))}
                      className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-sm ${
                        active ? "border-accent bg-accent-soft" : "border-line hover:bg-panel-sunk"
                      }`}
                    >
                      {w.color_slot && <span className="h-2.5 w-2.5 rounded-full" style={{ background: slotColor(w.color_slot) }} />}
                      <span>
                        <span className="block text-ink-2">{w.name}</span>
                        <span className={`block font-semibold tnum ${w.balance < 0 ? "text-critical" : ""}`}>{money(w.balance, w.currency)}</span>
                      </span>
                    </button>
                  );
                },
              )}
            </div>
          </section>

          <div role="radiogroup" aria-label="Period" className="flex w-fit gap-1 rounded-full bg-panel p-1 text-sm font-medium">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                role="radio"
                aria-checked={period === p.value}
                onClick={() => setPeriod(p.value)}
                className={`rounded-full px-3.5 py-1.5 ${period === p.value ? "bg-accent text-accent-ink" : "text-ink-2"}`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <SortablePanels
            order={layout}
            onChange={(order) => {
              setLayout(order);
              api("/settings", { method: "PUT", json: { overview_layout: order } });
            }}
            items={[
              {
                id: "networth",
                wide: true,
                node: (
                  <Panel title="Net worth" note="All wallets, in USD">
                    {data.networth.length > 1 ? (
                      <>
                        <dl className="mb-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
                          {(["net", "assets", "debts"] as const).map((key) => (
                            <div key={key}>
                              <dt className="text-ink-2">{{ net: "Net worth", assets: "Assets", debts: "Debts" }[key]}</dt>
                              <dd className="font-display text-xl font-semibold tnum">{money(data.networth.at(-1)![key])}</dd>
                            </div>
                          ))}
                        </dl>
                        <NetWorthChart data={data.networth} />
                      </>
                    ) : (
                      <Empty>Net worth appears after your first month of transactions.</Empty>
                    )}
                  </Panel>
                ),
              },
              { id: "month", node: <MonthSummary wallet={wallet} refresh={data} /> },
              {
                id: "goals",
                node: (
                  <Panel title="Goals" note={<a className="text-accent" href="/goals/">All goals</a>}>
                    <GoalsPanel goals={data.goals} />
                  </Panel>
                ),
              },
              {
                id: "categories",
                node: (
                  <Panel title="Where it went" note={PERIODS.find((p) => p.value === period)!.label}>
                    <CategoryDonut data={data.categories} />
                  </Panel>
                ),
              },
              {
                id: "cashflow",
                node: (
                  <Panel title="In vs out" note={bucket === "day" ? "Per day" : "Per month"}>
                    <CashflowChart data={data.cashflow} bucket={bucket} />
                  </Panel>
                ),
              },
              {
                id: "budgets",
                wide: true,
                node: (
                  <Panel title={data.style === "50_30_20" ? "50/30/20 this month" : "Budgets this month"} note={selected && "Across all wallets"}>
                    {data.style === "50_30_20" ? (
                      <GroupBars plan={data.plan} />
                    ) : (
                      <>
                        {data.style === "zero_based" && (
                          <div className="mb-5">
                            <ZeroBasedSummary plan={data.plan} />
                          </div>
                        )}
                        <BudgetBars rows={data.budgets} />
                      </>
                    )}
                  </Panel>
                ),
              },
              {
                id: "biggest",
                node: (
                  <Panel title="Biggest expenses">
                    <RankedBars
                      rows={data.merchants.largest.map((t) => ({
                        key: t.id,
                        label: t.merchant || "Unknown",
                        sub: shortDate(t.date),
                        value: t.amount,
                        display: money(t.amount),
                      }))}
                    />
                  </Panel>
                ),
              },
              {
                id: "visited",
                node: (
                  <Panel title="Most visited">
                    <RankedBars
                      rows={data.merchants.frequent.map((m) => ({
                        key: m.merchant,
                        label: m.merchant || "Unknown",
                        sub: money(m.total),
                        value: m.count,
                        display: `${m.count} ${m.count === 1 ? "visit" : "visits"}`,
                      }))}
                    />
                  </Panel>
                ),
              },
              {
                id: "pace",
                wide: true,
                node: (
                  <Panel
                    title="Spending pace"
                    note={paceDelta !== null && `${money(Math.abs(paceDelta))} ${paceDelta > 0 ? "more" : "less"} than this point last month`}
                  >
                    <ComparisonChart data={data.comparison} />
                  </Panel>
                ),
              },
              {
                id: "upcoming",
                node: (
                  <Panel title="Coming up" note="Next 14 days">
                    {data.upcoming.length === 0 ? (
                      <p className="py-6 text-center text-sm text-ink-2">Nothing scheduled in the next two weeks.</p>
                    ) : (
                      <ul className="space-y-2.5 text-sm">
                        {data.upcoming.map((u) => (
                          <li key={`${u.rule_id}-${u.date}`} className="flex items-baseline gap-3">
                            <span className="w-12 shrink-0 text-ink-2 tnum">{shortDate(u.date)}</span>
                            <span className="mr-auto min-w-0">
                              <span className="block truncate">{u.merchant}</span>
                              <span className="block text-xs text-ink-2">
                                {u.kind === "transfer" ? `${walletName(u.wallet_id)} to ${walletName(u.to_wallet_id)}` : walletName(u.wallet_id)}
                              </span>
                            </span>
                            <span className={`tnum ${u.kind === "income" ? "text-up" : ""}`}>
                              {u.kind === "income" ? "+" : u.kind === "expense" ? "−" : ""}
                              {money(u.amount, data.wallets.find((w) => w.id === u.wallet_id)?.currency)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>
                ),
              },
            ]}
          />
        </div>
      )}
      {adding && (
        <TransactionModal
          categories={categories}
          wallets={data?.wallets ?? []}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            load();
          }}
        />
      )}
    </Shell>
  );
}
