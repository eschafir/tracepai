"use client";

import { useEffect } from "react";

export default function Toast({
  message,
  action,
  onAction,
  onDone,
  duration = 6000,
}: {
  message: string;
  action?: string;
  onAction?: () => void;
  onDone: () => void;
  duration?: number;
}) {
  useEffect(() => {
    const timer = setTimeout(onDone, duration);
    return () => clearTimeout(timer);
  }, [message, onDone, duration]);

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center px-4">
      <div
        role="status"
        className="pointer-events-auto flex items-center gap-4 rounded-full bg-ink py-2.5 pr-2.5 pl-5 text-sm text-page shadow-lg"
      >
        <span>{message}</span>
        {action && (
          <button
            className="rounded-full px-3 py-1 font-semibold text-page underline-offset-2 hover:underline"
            onClick={onAction}
          >
            {action}
          </button>
        )}
      </div>
    </div>
  );
}
