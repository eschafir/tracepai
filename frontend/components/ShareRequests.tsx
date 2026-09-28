"use client";

import { useEffect, useState } from "react";
import { api, ApiError, ShareRequests as Requests } from "@/lib/api";

/** Shared wallets you're invited to and people sharing expenses with you. Nothing counts for you until you accept. */
export default function ShareRequests() {
  const [requests, setRequests] = useState<Requests | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Requests>("/shared/requests").then(setRequests);
  }, []);

  async function answer(path: string, accepted: boolean) {
    setError("");
    try {
      await api(path, { method: "POST" });
      if (accepted) window.location.reload(); // what was shared now counts everywhere on the page
      else setRequests(await api<Requests>("/shared/requests"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That didn't work. Check that TracepAI is running.");
    }
  }

  if (!requests || (!requests.wallets.length && !requests.people.length)) return null;

  const row = (key: string, text: string, base: string) => (
    <li key={key} className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <span className="mr-auto">{text}</span>
      <button className="btn btn-primary py-1" onClick={() => answer(`${base}/accept`, true)}>
        Accept
      </button>
      <button className="btn py-1" onClick={() => answer(`${base}/decline`, false)}>
        Decline
      </button>
    </li>
  );

  return (
    <section aria-label="Share requests" className="mb-4 rounded-2xl bg-panel p-4 text-sm">
      <ul className="space-y-3">
        {requests.wallets.map((w) => row(`w${w.id}`, `${w.owner} invited you to the shared wallet ${w.name}.`, `/shared/${w.id}`))}
        {requests.people.map((p) =>
          row(
            `p${p.id}`,
            `${p.username} shared ${p.expenses === 1 ? "an expense" : `${p.expenses} expenses`} with you. Accept to count your share of what they share with you.`,
            `/shared-expenses/people/${p.id}`,
          ),
        )}
      </ul>
      {error && (
        <p role="alert" className="mt-2 text-critical">
          {error}
        </p>
      )}
    </section>
  );
}
