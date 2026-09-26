"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { createContext, useContext } from "react";
import { money, moneyShort, monthLabel, shortDate, slotColor } from "@/lib/format";

const axis = { stroke: "var(--axis)", tick: { fill: "var(--muted)", fontSize: 12 }, tickLine: false };
const tooltip = {
  contentStyle: {
    background: "var(--panel)",
    border: "1px solid var(--line)",
    borderRadius: 10,
    color: "var(--ink)",
    fontSize: 13,
  },
  labelStyle: { color: "var(--ink-2)", marginBottom: 4 },
  itemStyle: { color: "var(--ink)", padding: 0 },
  formatter: (value: unknown) => money(Number(value)),
};

/** Set by SortablePanels: the grip that drags the panel it's in. */
export const DragHandle = createContext<((title: string) => React.ReactNode) | null>(null);

export function Panel({
  title,
  note,
  className = "",
  children,
}: {
  title: string;
  note?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  const handle = useContext(DragHandle);
  return (
    <section className={`rounded-2xl bg-panel p-5 ${className}`}>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          {handle?.(title)}
          {title}
        </h2>
        {note && <p className="text-sm text-ink-2">{note}</p>}
      </div>
      {children}
    </section>
  );
}

export function LegendKey({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4"
            style={{ borderTop: `2px ${item.dashed ? "dashed" : "solid"} ${item.color}` }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="grid h-48 place-items-center text-sm text-ink-2">{children}</p>;
}

export type BalancePoint = { date: string; balance: number };

export function BalanceChart({ data }: { data: BalancePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="balanceFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.22} />
            <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="date" {...axis} tickFormatter={shortDate} minTickGap={48} />
        <YAxis {...axis} axisLine={false} tickFormatter={moneyShort} width={56} />
        <Tooltip {...tooltip} labelFormatter={(d) => shortDate(String(d))} />
        <Area
          type="monotone"
          dataKey="balance"
          name="Balance"
          stroke="var(--series-1)"
          strokeWidth={2}
          fill="url(#balanceFill)"
          activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--panel)" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export type CategoryTotal = { category_id: number | null; name: string; color_slot: number | null; total: number };

export function CategoryDonut({ data }: { data: CategoryTotal[] }) {
  const rows =
    data.length > 8
      ? [...data.slice(0, 7), { category_id: -1, name: "Other", color_slot: null, total: data.slice(7).reduce((s, r) => s + r.total, 0) }]
      : data;
  const total = rows.reduce((s, r) => s + r.total, 0);
  if (!total) return <Empty>No spending in this period.</Empty>;
  const pieData = rows.map((r) => ({ ...r, fill: slotColor(r.color_slot) }));
  return (
    <div className="grid items-center gap-4 sm:grid-cols-[180px_1fr]">
      <div className="relative mx-auto h-[180px] w-[180px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={pieData}
              dataKey="total"
              nameKey="name"
              innerRadius={58}
              outerRadius={88}
              paddingAngle={1}
              stroke="var(--panel)"
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Tooltip {...tooltip} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
          <span className="text-xs text-ink-2">Spent</span>
          <span className="font-display text-lg font-semibold">{moneyShort(total)}</span>
        </div>
      </div>
      <ul className="space-y-1.5 text-sm">
        {rows.map((r) => (
          <li key={r.name} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: slotColor(r.color_slot) }} />
            <span className="truncate">{r.name}</span>
            <span className="ml-auto tnum text-ink-2">{Math.round((100 * r.total) / total)}%</span>
            <span className="w-20 text-right tnum">{money(r.total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export type CashflowPoint = { period: string; income: number; expense: number; net: number };

export function CashflowChart({ data, bucket }: { data: CashflowPoint[]; bucket: "day" | "month" }) {
  const label = (p: string) => (bucket === "day" ? shortDate(p) : monthLabel(p));
  return (
    <>
      <LegendKey
        items={[
          { label: "Income", color: "var(--series-1)" },
          { label: "Expenses", color: "var(--series-2)" },
        ]}
      />
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} barGap={2} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="period" {...axis} tickFormatter={label} minTickGap={24} />
          <YAxis {...axis} axisLine={false} tickFormatter={moneyShort} width={56} />
          <Tooltip {...tooltip} labelFormatter={(p) => label(String(p))} cursor={{ fill: "var(--panel-sunk)" }} />
          <Bar dataKey="income" name="Income" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={28} />
          <Bar dataKey="expense" name="Expenses" fill="var(--series-2)" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </>
  );
}

export type ComparisonPoint = { day: number; current: number | null; previous: number | null };

export function ComparisonChart({ data }: { data: ComparisonPoint[] }) {
  return (
    <>
      <LegendKey
        items={[
          { label: "This month", color: "var(--series-2)" },
          { label: "Last month", color: "var(--muted)", dashed: true },
        ]}
      />
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="day" {...axis} tickFormatter={(d) => `Day ${d}`} minTickGap={32} />
          <YAxis {...axis} axisLine={false} tickFormatter={moneyShort} width={56} />
          <Tooltip {...tooltip} labelFormatter={(d) => `Day ${d}`} />
          <Line
            type="monotone"
            dataKey="previous"
            name="Last month"
            stroke="var(--muted)"
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="current"
            name="This month"
            stroke="var(--series-2)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--panel)" }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

export type NetWorthPoint = { date: string; assets: number; debts: number; net: number };

const NET_SERIES = [
  { key: "net", label: "Net worth", color: "var(--series-1)" },
  { key: "assets", label: "Assets", color: "var(--series-2)", dashed: true },
  { key: "debts", label: "Debts", color: "var(--series-3)", dashed: true },
] as const;

// Month-end points, plus today as the last one. All values are USD.
export function NetWorthChart({ data }: { data: NetWorthPoint[] }) {
  const label = (d: unknown) => monthLabel(String(d).slice(0, 7));
  return (
    <>
      <LegendKey items={NET_SERIES.map(({ label, color, ...s }) => ({ label, color, dashed: "dashed" in s }))} />
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="date" {...axis} tickFormatter={label} minTickGap={32} />
          <YAxis {...axis} axisLine={false} tickFormatter={moneyShort} width={56} />
          <Tooltip {...tooltip} labelFormatter={(d) => (d === data.at(-1)?.date ? "Today" : `End of ${label(d)}`)} />
          {NET_SERIES.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={"dashed" in s ? "5 4" : undefined}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--panel)" }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

export function RankedBars({ rows }: { rows: { key: string | number; label: string; sub: string; value: number; display: string }[] }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  if (!rows.length) return <Empty>Nothing to rank in this period.</Empty>;
  return (
    <ol className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate" title={`${r.label}, ${r.sub}`}>
            {r.label}
            <span className="block text-xs text-ink-2">{r.sub}</span>
          </span>
          <span className="h-3 rounded-r bg-panel-sunk">
            <span
              className="block h-full rounded-r"
              style={{ width: `${(100 * r.value) / max}%`, background: "var(--series-1)" }}
            />
          </span>
          <span className="tnum">{r.display}</span>
        </li>
      ))}
    </ol>
  );
}

export type BudgetStatus = {
  budget_id: number;
  name: string;
  color_slot: number | null;
  limit: number;
  spent: number;
  percent: number;
  days_remaining: number;
  projected: number;
  alert: "over" | "pace" | null;
};

function budgetState(b: BudgetStatus) {
  if (b.percent >= 100) return { color: "var(--critical)", icon: "!", label: `Over by ${money(b.spent - b.limit)}` };
  if (b.alert === "pace") return { color: "var(--warning)", icon: "!", label: `On pace to go over by ${money(b.projected - b.limit)}` };
  if (b.percent >= 85) return { color: "var(--warning)", icon: "!", label: "Close to limit" };
  return { color: "var(--series-1)", icon: null, label: `${money(b.limit - b.spent)} left` };
}

export function BudgetBars({ rows }: { rows: BudgetStatus[] }) {
  if (!rows.length) return <Empty>No budgets yet. Add one on the Budgets page.</Empty>;
  return (
    <ul className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
      {rows.map((b) => {
        const state = budgetState(b);
        return (
          <li key={b.budget_id} className="text-sm">
            <div className="mb-1.5 flex items-baseline gap-2">
              <span className="font-medium">{b.name}</span>
              <span className="ml-auto tnum text-ink-2">
                {money(b.spent)} of {money(b.limit)}
              </span>
            </div>
            <div
              className="h-2.5 overflow-hidden rounded-full bg-panel-sunk"
              role="progressbar"
              aria-label={`${b.name} budget`}
              aria-valuenow={Math.round(b.percent)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.min(b.percent, 100)}%`, background: state.color }}
              />
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-2">
              {state.icon && (
                <span
                  aria-hidden
                  className="grid h-3.5 w-3.5 place-items-center rounded-full text-[10px] font-bold text-white"
                  style={{ background: state.color === "var(--warning)" ? "#b37a00" : state.color }}
                >
                  {state.icon}
                </span>
              )}
              <span>
                {Math.round(b.percent)}% used, {state.label}
                {b.days_remaining > 0 && `, ${b.days_remaining} days left`}
              </span>
            </p>
          </li>
        );
      })}
    </ul>
  );
}
