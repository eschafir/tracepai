"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Category, Transaction } from "@/lib/api";
import { money, shortDate, slotColor } from "@/lib/format";

type Located = Transaction & { lat: number; lng: number };

function FitToMarkers({ points }: { points: Located[] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 1) map.setView([points[0].lat, points[0].lng], 15);
    else if (points.length) map.fitBounds(points.map((p) => [p.lat, p.lng] as [number, number]), { padding: [32, 32], maxZoom: 15 });
  }, [map, points]);
  return null;
}

export default function SpendingMap({
  transactions,
  categories,
}: {
  transactions: Transaction[];
  categories: Map<number, Category>;
}) {
  const points = transactions.filter((t): t is Located => t.lat != null && t.lng != null);

  if (!points.length) {
    return (
      <p className="p-10 text-center text-ink-2">
        No transactions with a location in this list. Add a place when you add or edit a transaction.
      </p>
    );
  }

  return (
    <div className="relative">
      <MapContainer center={[points[0].lat, points[0].lng]} zoom={13} scrollWheelZoom className="spending-map h-[60vh] min-h-80 w-full">
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />
        <FitToMarkers points={points} />
        {points.map((t) => {
          const category = t.splits.length ? null : t.category_id ? categories.get(t.category_id) : undefined;
          const categoryName = t.splits.length ? "Split" : (category?.name ?? "Uncategorized");
          return (
            <CircleMarker
              key={t.id}
              center={[t.lat, t.lng]}
              radius={8}
              pathOptions={{
                color: "#ffffff",
                weight: 2,
                fillColor: slotColor(category?.color_slot),
                fillOpacity: 0.9,
              }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {t.merchant || t.place}, {money(t.amount)}
              </Tooltip>
              <Popup>
                <strong>{t.merchant || "No merchant"}</strong>
                <br />
                {t.kind === "income" ? "+" : "−"}
                {money(t.amount)} on {shortDate(t.date)}
                <br />
                {categoryName}
                {t.place && (
                  <>
                    <br />
                    {t.place}
                  </>
                )}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <p className="px-4 py-2 text-xs text-ink-2">
        {points.length} of {transactions.length} transactions in this list have a place.
      </p>
    </div>
  );
}
