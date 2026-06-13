import { useState } from "react";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { InviteResponse } from "../types";

export function AdminInvites() {
  const { user } = useAuth();
  const [email, setEmail] = useState("");
  const [invite, setInvite] = useState<InviteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!user?.is_admin) {
    return <p className="p-6 text-red-600">Admin only.</p>;
  }

  async function createInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await api.createInvite(email);
      setInvite(result);
    } catch (err) {
      setError(errorMessage(err, "Failed to create invite"));
    } finally {
      setLoading(false);
    }
  }

  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const inviteUrl = invite ? `${origin}${invite.invite_url}` : "";

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Invite Users</h1>
        <p className="text-sm text-slate-500 mt-1">
          Generate one-use registration tokens for new users.
        </p>
      </div>

      <form onSubmit={createInvite} className="space-y-3">
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Email lock</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            placeholder="Optional"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create invite"}
        </button>
      </form>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {invite && (
        <div className="border border-slate-200 rounded-lg bg-white p-4 space-y-3">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Invite token</p>
            <p className="font-mono text-sm text-slate-900 break-all">{invite.token}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Invite URL</p>
            <p className="font-mono text-sm text-slate-900 break-all">{inviteUrl}</p>
          </div>
          <p className="text-xs text-slate-500">
            Expires {new Date(invite.expires_at).toLocaleString()}. Tokens are single-use.
          </p>
        </div>
      )}
    </div>
  );
}
