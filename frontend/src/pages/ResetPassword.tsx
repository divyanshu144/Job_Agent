import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useState } from "react";
import { ArrowRight, KeyRound, Sparkles } from "lucide-react";
import { api, errorMessage } from "../api/client";

export function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.confirmPasswordReset(token, password);
      navigate("/login");
    } catch (err) {
      setError(errorMessage(err, "Password reset failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f6f5f2] p-4">
      <div className="w-full max-w-md rounded-3xl border border-zinc-200 bg-white p-8 shadow-[0_24px_80px_rgba(24,24,27,0.10)]">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-zinc-950 text-white">
            <Sparkles className="size-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-950">JobFit</p>
            <p className="text-xs text-zinc-500">Application support service</p>
          </div>
        </div>
        <div className="space-y-6">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
            <KeyRound className="size-3.5" />
            New credential
          </div>
          <h1 className="text-2xl font-bold text-slate-950">Choose new password</h1>
          <p className="mt-1 text-sm text-slate-500">Set a new password for your account.</p>
        </div>
        {!token && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            Missing reset token.
          </p>
        )}
        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">New password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-sm shadow-sm shadow-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
            />
            <p className="text-xs text-slate-400">Minimum 8 characters</p>
          </div>
          <button
            type="submit"
            disabled={loading || !token}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
          >
            {loading ? "Updating password..." : "Update password"}
            {!loading && <ArrowRight className="size-4" />}
          </button>
        </form>
        <p className="text-center text-xs text-slate-400">
          <Link to="/login" className="font-medium text-slate-700 hover:text-slate-950">Back to sign in</Link>
        </p>
        </div>
      </div>
    </div>
  );
}
