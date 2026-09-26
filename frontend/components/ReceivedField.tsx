"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// For a transfer between wallets in different currencies: the amount that arrived, pre-filled from the day's rate.
export default function ReceivedField({ amount, from, to, date, value, onChange, className = "field mt-1.5" }: {
  amount: string;
  from?: string;
  to?: string;
  date: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  const [edited, setEdited] = useState(value !== "");
  const differs = Boolean(from && to && from !== to);

  useEffect(() => {
    if (edited || !differs || !Number(amount)) return;
    const params = new URLSearchParams({ amount, source: from!, to: to!, date });
    api<{ amount: number }>(`/fx/convert?${params}`)
      .then((r) => onChange(String(r.amount)))
      .catch(() => {});
  }, [amount, from, to, date, edited, differs, onChange]);

  if (!differs) return null;
  return (
    <label className="block text-sm font-medium">
      Received ({to})
      <input
        className={`${className} tnum`}
        type="number"
        inputMode="decimal"
        min="0.01"
        step="0.01"
        required
        value={value}
        onChange={(e) => {
          setEdited(true);
          onChange(e.target.value);
        }}
      />
      <span className="mt-1 block text-xs font-normal text-ink-2">
        Estimated from the {from === "ARS" || to === "ARS" ? "official BNA" : "day's"} rate. Change it to what you actually got.
      </span>
    </label>
  );
}
