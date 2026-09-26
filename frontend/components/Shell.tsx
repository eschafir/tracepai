"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/transactions/", label: "Transactions" },
  { href: "/wallets/", label: "Wallets" },
  { href: "/budgets/", label: "Budgets" },
  { href: "/goals/", label: "Goals" },
  { href: "/recurring/", label: "Recurring" },
  { href: "/review/", label: "Year" },
];

export default function Shell({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    api<{ username: string }>("/auth/me").then((me) => setUser(me.username));
  }, []);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login/";
  }

  if (!user) return null;

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
      <header className="flex flex-wrap items-center gap-x-8 gap-y-3 py-5">
        <Link href="/" className="font-display text-2xl font-bold tracking-tight">
          Tracep<span className="text-accent">AI</span>
        </Link>
        <nav className="order-last flex w-full flex-wrap gap-1 sm:order-none sm:w-auto">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname === item.href.replace(/\/$/, "");
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-full px-3 py-1.5 text-sm font-medium whitespace-nowrap ${
                  active ? "bg-accent-soft text-ink" : "text-ink-2 hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {actions}
          <span className="text-sm text-ink-2">{user}</span>
          <button onClick={logout} className="text-sm text-ink-2 hover:text-ink" title={`Signed in as ${user}`}>
            Log out
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
