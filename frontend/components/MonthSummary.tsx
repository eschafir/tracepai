"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/charts";
import { api, MonthSummary as Summary } from "@/lib/api";
import { iso, money, parseIso, shortDate } from "@/lib/format";

const thisMonth = () => iso(new Date()).slice(0, 7);

function shiftMonth(month: string, by: number) {
  const d = parseIso(`${month}-01`);
  d.setMonth(d.getMonth() + by);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function MonthSummary({ wallet, refresh }: { wallet: string; refresh: unknown }) {
  const [month, setMonth] = useState(thisMonth);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ month, ...(wallet && { wallet }) });
    api<Summary>(`/analytics/summary?${params}`).then(setSummary);
  }, [month, wallet, refresh]);

  const name = parseIso(`${month}-01`).toLocaleDateString("en-US", {
    month: "long",
    ...(month.slice(0, 4) !== thisMonth().slice(0, 4) && { year: "numeric" }),
  });
  const s = summary?.month === month ? summary : null;

  const arrows = (
    <span className="flex items-center gap-1">
      <button className="btn px-3 py-1" aria-label="Previous month" onClick={() => setMonth(shiftMonth(month, -1))}>
        &lsaquo;
      </button>
      <button
        className="btn px-3 py-1"
        aria-label="Next month"
        disabled={month >= thisMonth()}
        onClick={() => setMonth(shiftMonth(month, 1))}
      >
        &rsaquo;
      </button>
    </span>
  );

  return (
    <Panel title={s?.in_progress ? `${name} so far` : name} note={arrows}>
      {s && !s.expenses && !s.income ? (
        <p className="py-6 text-center text-sm text-ink-2">No transactions in {name}.</p>
      ) : (
        s && (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-ink-2">Spent</dt>
              <dd>
                <span className="font-display text-2xl font-semibold tnum">{money(s.expenses)}</span>
                {s.change_percent !== null && (
                  <span className={`ml-2 ${s.change > 0 ? "text-critical" : "text-up"}`}>
                    {Math.abs(s.change_percent)}% {s.change > 0 ? "more" : "less"} than{" "}
                    {s.in_progress ? `by day ${s.compared_days} last month` : "the month before"}
                  </span>
                )}
              </dd>
            </div>
            {s.top_category && (
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-ink-2">Top category</dt>
                <dd>
                  {s.top_category.name}, {money(s.top_category.total)}
                  {s.top_category.share !== null && ` (${Math.round(s.top_category.share)}%)`}
                </dd>
              </div>
            )}
            {s.biggest && (
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-ink-2">Biggest purchase</dt>
                <dd>
                  {s.biggest.merchant || "No merchant"}, {money(s.biggest.amount)} on {shortDate(s.biggest.date)}
                </dd>
              </div>
            )}
            {s.most_visited && (
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-ink-2">Most visited</dt>
                <dd>
                  {s.most_visited.merchant}, {s.most_visited.count} {s.most_visited.count === 1 ? "time" : "times"}
                </dd>
              </div>
            )}
            <div className="flex gap-2">
              <dt className="w-32 shrink-0 text-ink-2">Budgets</dt>
              <dd className={s.over_budget.length ? "text-critical" : ""}>
                {s.over_budget.length ? `Over on ${s.over_budget.join(", ")}` : "All within their limits"}
              </dd>
            </div>
            {s.savings_rate !== null && (
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-ink-2">Kept</dt>
                <dd className={s.savings_rate < 0 ? "text-critical" : "text-up"}>
                  {s.savings_rate >= 0
                    ? `${Math.round(s.savings_rate)}% of income`
                    : `Spent ${money(-s.net)} more than came in`}
                </dd>
              </div>
            )}
          </dl>
        )
      )}
    </Panel>
  );
}
