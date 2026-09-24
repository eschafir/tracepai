"use client";

import { useState } from "react";
import { api, ApiError, Place } from "@/lib/api";

export type Location = { place: string; lat: number; lng: number };

export function PinIcon({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 20 20" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M10 17.5s5.5-5.1 5.5-9.25a5.5 5.5 0 1 0-11 0C4.5 12.4 10 17.5 10 17.5z" strokeLinejoin="round" />
      <circle cx="10" cy="8.25" r="2" />
    </svg>
  );
}

export default function LocationField({
  value,
  source,
  onChange,
}: {
  value: Location | null;
  source?: string;
  onChange: (location: Location | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canLocate = typeof window !== "undefined" && window.isSecureContext && "geolocation" in navigator;

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const found = await api<Place[]>(`/places/search?${new URLSearchParams({ q: query })}`);
      setResults(found);
      if (!found.length) setError("No places found. Try adding the city.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Place search failed.");
    } finally {
      setBusy(false);
    }
  }

  function locate() {
    setBusy(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const lat = Number(coords.latitude.toFixed(6));
        const lng = Number(coords.longitude.toFixed(6));
        try {
          const place = await api<Place>(`/places/reverse?lat=${lat}&lng=${lng}`);
          onChange({ place: place.name || "Current location", lat, lng });
        } catch {
          onChange({ place: "Current location", lat, lng });
        }
        setBusy(false);
      },
      () => {
        setError("Location access was blocked. Search for the place instead.");
        setBusy(false);
      },
    );
  }

  if (value) {
    return (
      <div className="text-sm font-medium">
        Place
        <div className="mt-1.5 flex items-center gap-2 rounded-[10px] border border-line px-3 py-2 font-normal">
          <span className="text-accent">
            <PinIcon />
          </span>
          <span className="mr-auto min-w-0">
            <span className="block truncate">{value.place}</span>
            {source && <span className="block text-xs text-ink-2">{source}</span>}
          </span>
          <button type="button" className="text-ink-2 hover:text-critical" onClick={() => onChange(null)}>
            Remove
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="text-sm font-medium">
      <label htmlFor="place-search">Place</label>
      <div className="mt-1.5 flex gap-2">
        <input
          id="place-search"
          className="field"
          placeholder="Shop, restaurant or address"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
        />
        <button type="button" className="btn shrink-0" onClick={search} disabled={busy || !query.trim()}>
          Search
        </button>
      </div>
      {canLocate && (
        <button type="button" className="mt-2 text-sm font-medium text-accent" onClick={locate} disabled={busy}>
          Use my location
        </button>
      )}
      {error && <p className="mt-1.5 text-sm font-normal text-critical">{error}</p>}
      {results && results.length > 0 && (
        <ul className="mt-2 divide-y divide-line rounded-[10px] border border-line font-normal">
          {results.map((r) => (
            <li key={`${r.lat},${r.lng}`}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left hover:bg-panel-sunk"
                onClick={() => {
                  onChange({ place: r.name, lat: r.lat, lng: r.lng });
                  setResults(null);
                  setQuery("");
                }}
              >
                <span className="block">{r.name}</span>
                <span className="block truncate text-xs text-ink-2">{r.address}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
