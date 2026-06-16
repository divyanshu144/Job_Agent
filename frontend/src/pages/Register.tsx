import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { ArrowRight, MailPlus, Sparkles } from "lucide-react";
import { errorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";

export function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inviteTokenFromUrl = searchParams.get("token") ?? "";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteToken, setInviteToken] = useState(inviteTokenFromUrl);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(email, password, inviteToken.trim() || undefined);
      navigate("/");
    } catch (err) {
      setError(errorMessage(err, "Registration failed"));
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
            <p className="text-xs text-slate-500">Account access</p>
          </div>
        </div>
        <div className="space-y-6">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
            <MailPlus className="size-3.5" />
            Invite-based access
          </div>
          <h1 className="text-2xl font-bold text-slate-950">Create account</h1>
          {inviteToken ? (
            <p className="mt-1 text-sm text-emerald-600">Invite token added.</p>
          ) : (
            <p className="mt-1 text-sm text-slate-500">First user gets admin access.</p>
          )}
        </div>
        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
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
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm shadow-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-300"
            />
            <p className="text-xs text-slate-400">Minimum 8 characters</p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">Invite token</label>
            <input
              value={inviteToken}
              onChange={(e) => setInviteToken(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 font-mono text-sm shadow-sm shadow-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-300"
              placeholder="Required after the first admin account"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-950 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-900 disabled:opacity-50"
          >
            {loading ? "Creating account..." : "Create account"}
            {!loading && <ArrowRight className="size-4" />}
          </button>
        </form>
        <p className="text-center text-xs text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-slate-700 hover:text-slate-950">Sign in</Link>
        </p>
        </div>
      </div>
    </div>
  );
}
