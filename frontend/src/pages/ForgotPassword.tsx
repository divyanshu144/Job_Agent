import { Link } from "react-router-dom";
import { useState } from "react";
import { ArrowRight, KeyRound, Sparkles } from "lucide-react";
import { api, errorMessage } from "../api/client";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [resetUrl, setResetUrl] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setResetUrl(null);
    setLoading(true);
    try {
      const result = await api.requestPasswordReset(email.trim());
      setMessage(result.message);
      if (result.reset_url) setResetUrl(result.reset_url);
    } catch (err) {
      setError(errorMessage(err, "Password reset failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#f8fafc_0%,#eef2f7_100%)] p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/70">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-indigo-950 text-white">
            <Sparkles className="size-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-950">JobFit Agent</p>
            <p className="text-xs text-slate-500">Account recovery</p>
          </div>
        </div>
        <div className="space-y-6">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
            <KeyRound className="size-3.5" />
            Password reset
          </div>
          <h1 className="text-2xl font-bold text-slate-950">Reset password</h1>
          <p className="mt-1 text-sm text-slate-500">Enter your account email.</p>
        </div>
        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
        )}
        {message && (
          <div className="space-y-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            <p>{message}</p>
            {resetUrl && (
              <Link to={resetUrl} className="inline-flex items-center gap-1 font-medium text-emerald-900 hover:underline">
                Open reset link
                <ArrowRight className="size-3.5" />
              </Link>
            )}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm shadow-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-300"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-950 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-900 disabled:opacity-50"
          >
            {loading ? "Creating reset link..." : "Create reset link"}
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
