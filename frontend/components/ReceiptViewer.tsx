"use client";

import { useEffect } from "react";

export function ReceiptIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path d="M5 2.75h6.5L15.25 6.5v10.75H5z" strokeLinejoin="round" />
      <path d="M11.5 2.75V6.5h3.75" strokeLinejoin="round" />
      <path d="M7.5 10h5M7.5 13h5" strokeLinecap="round" />
    </svg>
  );
}

export function ReceiptButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`View receipt for ${label}`}
      title="View receipt"
      className="inline-grid h-8 w-8 place-items-center rounded-lg border border-line text-ink-2 hover:bg-panel-sunk hover:text-ink"
    >
      <ReceiptIcon />
    </button>
  );
}

export default function ReceiptViewer({ path, title, onClose }: { path: string; title: string; onClose: () => void }) {
  const url = `/api/receipts/${path}`;
  const isPdf = path.toLowerCase().endsWith(".pdf");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Receipt for ${title}`}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-full w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-panel"
      >
        <div className="flex items-center gap-4 border-b border-line px-5 py-3">
          <h2 className="mr-auto truncate font-display text-lg font-semibold">{title}</h2>
          <a href={url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">
            Open in new tab
          </a>
          <button type="button" onClick={onClose} className="text-sm text-ink-2 hover:text-ink">
            Close
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-panel-sunk">
          {isPdf ? (
            <iframe src={url} title={`Receipt for ${title}`} className="h-[80vh] w-full" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={`Receipt for ${title}`} className="mx-auto max-h-[80vh] w-auto object-contain" />
          )}
        </div>
      </div>
    </div>
  );
}
