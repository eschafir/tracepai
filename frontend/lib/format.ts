const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact" });

export const money = (value: number) => currency.format(value);
export const moneyShort = (value: number) => compact.format(value);

export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const parseIso = (s: string) => new Date(`${s}T00:00:00`);

export const shortDate = (s: string) => parseIso(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const monthLabel = (s: string) =>
  parseIso(`${s}-01`).toLocaleDateString("en-US", { month: "short", year: "2-digit" });

export const slotColor = (slot: number | null | undefined) => (slot ? `var(--series-${slot})` : "var(--muted)");

export type Period = "week" | "month" | "year";

export function periodRange(period: Period, today = new Date()) {
  const start = new Date(today);
  if (period === "week") start.setDate(today.getDate() - 6);
  if (period === "month") start.setDate(1);
  if (period === "year") start.setMonth(0, 1);
  return { start: iso(start), end: iso(today) };
}
