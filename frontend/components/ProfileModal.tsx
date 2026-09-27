"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function ProfileModal({
  currentUsername,
  currentDisplayName,
  onClose,
  onUpdated,
}: {
  currentUsername: string;
  currentDisplayName: string;
  onClose: () => void;
  onUpdated: (newDisplayName: string) => void;
}) {
  const [displayName, setDisplayName] = useState(currentDisplayName || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (newPassword && newPassword !== confirmPassword) {
      setError("New passwords do not match.");
      return;
    }
    if (newPassword && !currentPassword) {
      setError("Current password is required to set a new password.");
      return;
    }
    if (newPassword && newPassword.length < 8) {
      setError("New password must be at least 8 characters long.");
      return;
    }

    setBusy(true);
    try {
      const payload: { display_name?: string; password?: string; current_password?: string } = {
        display_name: displayName.trim(),
      };
      if (newPassword) {
        payload.password = newPassword;
        payload.current_password = currentPassword;
      }
      const res = await api<{ id: number; username: string; display_name: string }>("/auth/profile", {
        method: "PUT",
        json: payload,
      });

      setSuccess("Profile updated successfully!");
      onUpdated(res.display_name);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setTimeout(() => {
        onClose();
      }, 1200);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update profile.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-title"
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-panel p-6 sm:rounded-3xl sm:max-w-md"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 id="profile-title" className="font-display text-xl font-semibold">
            Profile Settings
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-ink-2 hover:text-ink">
            Cancel
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-ink-2">Username</label>
            <input
              type="text"
              disabled
              value={currentUsername}
              className="field mt-1 bg-ink/5 text-ink-2 cursor-not-allowed"
            />
          </div>

          <div>
            <label className="block text-sm font-medium">Display Name</label>
            <input
              type="text"
              value={displayName}
              placeholder={currentUsername}
              onChange={(e) => setDisplayName(e.target.value)}
              className="field mt-1"
            />
            <p className="mt-1 text-xs text-ink-2">This name is displayed in the navigation header.</p>
          </div>

          <div className="border-t border-ink/10 pt-4">
            <h3 className="text-sm font-semibold mb-3">Change Password</h3>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-ink-2">Current Password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="Required only to change password"
                  className="field mt-1"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-ink-2">New Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="field mt-1"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-ink-2">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-type new password"
                  className="field mt-1"
                />
              </div>
            </div>
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}
          {success && <p className="text-sm text-emerald-600 font-medium">{success}</p>}

          <div className="flex justify-end gap-3 pt-3">
            <button type="button" className="btn" onClick={onClose} disabled={busy}>
              Close
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Saving..." : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
