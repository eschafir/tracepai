const formatters = new Map<string, Intl.NumberFormat>();
const formatter = (currency: string, notation?: "compact") => {
  const key = `${currency}-${notation}`;
  if (!formatters.has(key)) formatters.set(key, new Intl.NumberFormat("en-US", { style: "currency", currency, notation }));
  return formatters.get(key)!;
};

// Totals and charts are in USD; a wallet's own amounts are in its currency.
export const money = (value: number, currency = "USD") => formatter(currency).format(value);
export const moneyShort = (value: number) => formatter("USD", "compact").format(value);

export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

// The browser's month, "2026-09"; month-based analytics take it so they match the user's calendar, not the server's.
export const thisMonth = () => iso(new Date()).slice(0, 7);

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

export const currencySymbol = (currency: string) =>
  formatter(currency).formatToParts(0).find((p) => p.type === "currency")?.value ?? currency;
