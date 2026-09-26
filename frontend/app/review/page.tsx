"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { CashflowChart, CategoryDonut, Empty, Panel, RankedBars } from "@/components/charts";
import SortablePanels from "@/components/SortablePanels";
import { api, Settings, YearReview } from "@/lib/api";
import { money, parseIso, shortDate } from "@/lib/format";

const monthName = (period: string) => parseIso(`${period}-01`).toLocaleDateString("en-US", { month: "long" });

export default function ReviewPage() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [review, setReview] = useState<YearReview | null>(null);
  const [layout, setLayout] = useState<string[]>([]);

  useEffect(() => {
    api<Settings>("/settings").then((s) => setLayout(s.year_layout));
  }, []);

  useEffect(() => {
    api<YearReview>(`/analytics/year?year=${year}`).then(setReview);
  }, [year]);

  const r = review?.year === year ? review : null;
  const empty = r && r.income === 0 && r.expenses === 0;

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto font-display text-3xl font-bold tracking-tight">
          {year} {r?.in_progress ? "so far" : "in review"}
        </h1>
        <span className="flex gap-2">
          <button className="btn" aria-label="Previous year" onClick={() => setYear(year - 1)}>
            &lsaquo; {year - 1}
          </button>
          <button className="btn" aria-label="Next year" onClick={() => setYear(year + 1)} disabled={year >= thisYear}>
            {year + 1} &rsaquo;
          </button>
        </span>
      </div>

      {r && empty && (
        <section className="rounded-2xl bg-panel p-8 text-center text-ink-2">No income or spending recorded in {year}.</section>
      )}

      {r && !empty && (
        <div className="space-y-4">
          <section className="rounded-2xl bg-panel p-5 sm:p-7">
            <dl className="flex flex-wrap gap-x-10 gap-y-3">
              <div>
                <dt className="text-sm text-ink-2">Came in</dt>
                <dd className="font-display text-3xl font-bold tnum">{money(r.income)}</dd>
              </div>
              <div>
                <dt className="text-sm text-ink-2">Went out</dt>
                <dd className="font-display text-3xl font-bold tnum">{money(r.expenses)}</dd>
              </div>
              <div>
                <dt className="text-sm text-ink-2">{r.net >= 0 ? "Kept" : "Spent more than came in"}</dt>
                <dd className={`font-display text-3xl font-bold tnum ${r.net >= 0 ? "text-up" : "text-critical"}`}>
                  {money(Math.abs(r.net))}
                  {r.savings_rate !== null && r.net >= 0 && <span className="ml-2 text-lg font-semibold">({r.savings_rate}%)</span>}
                </dd>
              </div>
            </dl>
            <ul className="mt-5 space-y-1.5 text-sm">
              {r.change_percent !== null && (
                <li>
                  Spent {Math.abs(r.change_percent)}% {r.change_percent > 0 ? "more" : "less"} than in {year - 1} (
                  {money(r.previous_expenses)}){r.in_progress && `, for the whole of ${year - 1}`}.
                </li>
              )}
              {r.busiest_month && (
                <li>
                  Busiest month: {monthName(r.busiest_month.month)}, with {money(r.busiest_month.expense)} spent.
                </li>
              )}
              {r.categories[0] && (
                <li>
                  Most went to {r.categories[0].name}: {money(r.categories[0].total)} ({r.categories[0].share}%).
                </li>
              )}
              <li>
                Net worth went from {money(r.net_worth_start)} to {money(r.net_worth_end)}
                {r.in_progress ? " so far" : ""}.
              </li>
              {r.goals.map((g) => (
                <li key={g.name}>
                  {g.name}: {g.gained >= 0 ? "added" : "took out"} {money(Math.abs(g.gained), g.currency)}.
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-ink-2">All amounts in USD, converted at each day&apos;s rate.</p>
          </section>

          <SortablePanels
            order={layout}
            onChange={(order) => {
              setLayout(order);
              api("/settings", { method: "PUT", json: { year_layout: order } });
            }}
            items={[
              {
                id: "months",
                wide: true,
                node: (
                  <Panel title="Month by month">
                    <CashflowChart data={r.months} bucket="month" />
                  </Panel>
                ),
              },
              {
                id: "categories",
                node: (
                  <Panel title="Where it went">
                    <CategoryDonut data={r.categories} />
                  </Panel>
                ),
              },
              {
                id: "largest",
                node: (
                  <Panel title="Biggest purchases">
                    {r.largest.length ? (
                      <RankedBars
                        rows={r.largest.map((t) => ({
                          key: t.id,
                          label: t.merchant || "No merchant",
                          sub: shortDate(t.date),
                          value: t.amount,
                          display: money(t.amount),
                        }))}
                      />
                    ) : (
                      <Empty>No purchases this year.</Empty>
                    )}
                  </Panel>
                ),
              },
              {
                id: "frequent",
                wide: true,
                node: (
                  <Panel title="Most visited">
                    <RankedBars
                      rows={r.frequent.map((m) => ({
                        key: m.merchant,
                        label: m.merchant || "No merchant",
                        sub: `${m.count} times`,
                        value: m.count,
                        display: money(m.total),
                      }))}
                    />
                  </Panel>
                ),
              },
            ]}
          />
        </div>
      )}
    </Shell>
  );
}
