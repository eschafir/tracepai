"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, Wallet } from "@/lib/api";
import ProfileModal from "@/components/ProfileModal";
import ImportDialog from "@/components/ImportDialog";
import ProfileImportModal from "@/components/ProfileImportModal";
import ShareRequests from "@/components/ShareRequests";

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
  const [displayName, setDisplayName] = useState<string>("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showImportCsv, setShowImportCsv] = useState(false);
  const [showImportProfile, setShowImportProfile] = useState(false);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<{ id: number; username: string; display_name: string }>("/auth/me").then((me) => {
      setUser(me.username);
      setDisplayName(me.display_name || me.username);
    });
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
        setExportOpen(false);
        setImportOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [menuOpen]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login/";
  }

  async function openImportCsv() {
    setMenuOpen(false);
    try {
      const ws = await api<Wallet[]>("/wallets");
      setWallets(ws);
    } catch {
      // ignore
    }
    setShowImportCsv(true);
  }

  function openImportProfile() {
    setMenuOpen(false);
    setShowImportProfile(true);
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
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(!menuOpen);
                setExportOpen(false);
                setImportOpen(false);
              }}
              className="flex items-center gap-1.5 rounded-full bg-accent-soft/50 px-3 py-1.5 text-sm font-medium text-ink hover:bg-accent-soft transition-colors cursor-pointer"
              aria-expanded={menuOpen}
              aria-haspopup="true"
            >
              <span>{displayName || user}</span>
              <svg
                className={`h-3.5 w-3.5 text-ink-2 transition-transform ${menuOpen ? "rotate-180" : ""}`}
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                  clipRule="evenodd"
                />
              </svg>
            </button>

            {menuOpen && (
              <div className="absolute right-0 mt-2 w-52 rounded-2xl bg-panel p-1.5 shadow-xl ring-1 ring-ink/10 z-50">
                <button
                  type="button"
                  onClick={() => {
                    setShowProfile(true);
                    setMenuOpen(false);
                  }}
                  className="flex w-full items-center px-3 py-2 text-sm font-medium rounded-xl hover:bg-accent-soft transition-colors text-ink cursor-pointer"
                >
                  Profile
                </button>

                <div className="py-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setExportOpen(!exportOpen);
                      setImportOpen(false);
                    }}
                    className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium rounded-xl hover:bg-accent-soft transition-colors text-ink cursor-pointer"
                  >
                    <span>Export</span>
                    <span className="text-xs text-ink-2">{exportOpen ? "▲" : "▼"}</span>
                  </button>
                  {exportOpen && (
                    <div className="ml-3 pl-2 border-l border-ink/10 space-y-0.5 my-1">
                      <a
                        href="/api/export?format=csv"
                        onClick={() => setMenuOpen(false)}
                        className="block px-3 py-1.5 text-sm rounded-lg hover:bg-accent-soft text-ink-2 hover:text-ink transition-colors cursor-pointer"
                      >
                        CSV
                      </a>
                      <a
                        href="/api/export/profile"
                        onClick={() => setMenuOpen(false)}
                        className="block px-3 py-1.5 text-sm rounded-lg hover:bg-accent-soft text-ink-2 hover:text-ink transition-colors cursor-pointer"
                      >
                        Profile
                      </a>
                    </div>
                  )}
                </div>

                <div className="py-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setImportOpen(!importOpen);
                      setExportOpen(false);
                    }}
                    className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium rounded-xl hover:bg-accent-soft transition-colors text-ink cursor-pointer"
                  >
                    <span>Import</span>
                    <span className="text-xs text-ink-2">{importOpen ? "▲" : "▼"}</span>
                  </button>
                  {importOpen && (
                    <div className="ml-3 pl-2 border-l border-ink/10 space-y-0.5 my-1">
                      <button
                        type="button"
                        onClick={openImportCsv}
                        className="block w-full text-left px-3 py-1.5 text-sm rounded-lg hover:bg-accent-soft text-ink-2 hover:text-ink transition-colors cursor-pointer"
                      >
                        CSV
                      </button>
                      <button
                        type="button"
                        onClick={openImportProfile}
                        className="block w-full text-left px-3 py-1.5 text-sm rounded-lg hover:bg-accent-soft text-ink-2 hover:text-ink transition-colors cursor-pointer"
                      >
                        Profile
                      </button>
                    </div>
                  )}
                </div>

                <div className="my-1 border-t border-ink/10" />

                <button
                  type="button"
                  onClick={logout}
                  className="flex w-full items-center px-3 py-2 text-sm font-medium rounded-xl text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors cursor-pointer"
                >
                  Log out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main>
        <ShareRequests />
        {children}
      </main>

      {showProfile && (
        <ProfileModal
          currentUsername={user}
          currentDisplayName={displayName}
          onClose={() => setShowProfile(false)}
          onUpdated={(newName) => setDisplayName(newName)}
        />
      )}

      {showImportCsv && (
        <ImportDialog
          wallets={wallets}
          onClose={() => setShowImportCsv(false)}
          onImported={() => {
            setShowImportCsv(false);
            window.location.reload();
          }}
        />
      )}

      {showImportProfile && (
        <ProfileImportModal
          onClose={() => setShowImportProfile(false)}
          onImported={() => {
            setShowImportProfile(false);
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}
