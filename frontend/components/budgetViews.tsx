import { BudgetStatus } from "@/components/charts";
import { BudgetGroup, BudgetPlan, PriceChange, Wallet } from "@/lib/api";
import { money } from "@/lib/format";

const GROUP_LABELS: Record<BudgetGroup, string> = { need: "Needs", want: "Wants", savings: "Savings" };

function StatusIcon({ critical }: { critical?: boolean }) {
  return (
    <span
      aria-hidden
      className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white"
      style={{ background: critical ? "var(--critical)" : "#b37a00" }}
    >
      !
    </span>
  );
}

// Budget pace alerts and subscription price changes, most urgent first.
export function Alerts({ budgets, prices, wallets }: { budgets: BudgetStatus[]; prices: PriceChange[]; wallets: Wallet[] }) {
  const currencyOf = (id: number) => wallets.find((w) => w.id === id)?.currency;
  const items = [
    ...budgets
      .filter((b) => b.alert === "over")
      .map((b) => ({ key: `b${b.budget_id}`, critical: true, href: "/budgets/", text: `${b.name} is over budget by ${money(b.spent - b.limit)}.` })),
    ...budgets
      .filter((b) => b.alert === "pace")
      .map((b) => ({
        key: `b${b.budget_id}`,
        critical: false,
        href: "/budgets/",
        text: `${b.name} is on pace to go over by ${money(b.projected - b.limit)} this month.`,
      })),
    ...prices.map((p) => ({
      key: `p${p.rule_id}`,
      critical: false,
      href: "/recurring/",
      text: `${p.merchant} charged ${money(p.new, currencyOf(p.wallet_id))}; the recurring item says ${money(p.old, currencyOf(p.wallet_id))}.`,
    })),
  ];
  if (!items.length) return null;
  const shown = items.slice(0, 3);
  return (
    <section role="status" aria-label="Alerts" className="rounded-2xl bg-panel p-4 sm:px-5">
      <ul className="space-y-2 text-sm">
        {shown.map((item) => (
          <li key={item.key} className="flex items-start gap-2">
            <StatusIcon critical={item.critical} />
            <a href={item.href} className="hover:underline">
              {item.text}
            </a>
          </li>
        ))}
      </ul>
      {items.length > shown.length && <p className="mt-2 text-xs text-ink-2">And {items.length - shown.length} more.</p>}
    </section>
  );
}

export function ZeroBasedSummary({ plan }: { plan: BudgetPlan }) {
  const left = plan.left_to_assign;
  return (
    <div className="text-sm">
      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        <div>
          <dt className="text-ink-2">Income this month</dt>
          <dd className="font-display text-xl font-semibold tnum">{money(plan.income)}</dd>
        </div>
        <div>
          <dt className="text-ink-2">Assigned to budgets</dt>
          <dd className="font-display text-xl font-semibold tnum">{money(plan.assigned)}</dd>
        </div>
        <div>
          <dt className="text-ink-2">{left >= 0 ? "Left to assign" : "Assigned over income"}</dt>
          <dd className={`font-display text-xl font-semibold tnum ${left < 0 ? "text-critical" : ""}`}>{money(Math.abs(left))}</dd>
        </div>
      </dl>
      <p className="mt-2 text-ink-2">
        {left > 0
          ? "Give every dollar a job: assign the rest to a category below."
          : left < 0
            ? "You've planned to spend more than came in. Lower some limits."
            : "Every dollar has a job."}{" "}
        Unspent money doesn&apos;t carry over to next month.
      </p>
    </div>
  );
}

export function GroupBars({ plan }: { plan: BudgetPlan }) {
  return (
    <div className="text-sm">
      <p className="mb-3 text-ink-2">
        Of {money(plan.income)} income this month: 50% for needs, 30% for wants, 20% saved.
      </p>
      <ul className="grid gap-4 sm:grid-cols-3">
        {plan.groups.map((g) => {
          const percent = g.target > 0 ? (100 * g.actual) / g.target : 0;
          // Needs and wants should stay under target; savings should reach it.
          const bad = g.group === "savings" ? g.actual < g.target : g.actual > g.target;
          return (
            <li key={g.group}>
              <div className="mb-1.5 flex items-baseline gap-2">
                <span className="font-medium">{GROUP_LABELS[g.group]}</span>
                <span className="ml-auto tnum text-ink-2">
                  {money(g.actual)} of {money(g.target)}
                </span>
              </div>
              <div
                className="h-2.5 overflow-hidden rounded-full bg-panel-sunk"
                role="progressbar"
                aria-label={`${GROUP_LABELS[g.group]}, compared with the target`}
                aria-valuenow={Math.round(percent)}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.max(0, Math.min(percent, 100))}%`, background: bad ? "var(--warning)" : "var(--series-1)" }}
                />
              </div>
              <p className="mt-1 flex items-start gap-1.5 text-xs text-ink-2">
                {bad && <StatusIcon />}
                {g.group === "savings"
                  ? bad
                    ? `${money(g.target - g.actual)} short of the target`
                    : "On target"
                  : bad
                    ? `${money(g.actual - g.target)} over the target`
                    : `${money(g.target - g.actual)} left`}
              </p>
            </li>
          );
        })}
      </ul>
      {plan.ungrouped.length > 0 && (
        <p className="mt-3 text-xs text-ink-2">
          Counted as wants until you choose a group: {plan.ungrouped.join(", ")}.
        </p>
      )}
    </div>
  );
}
