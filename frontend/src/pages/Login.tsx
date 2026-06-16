import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight, LockKeyhole, Sparkles } from "lucide-react";
import { errorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(errorMessage(err, "Login failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#f8fafc_0%,#eef2f7_100%)] p-4">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/70 md:grid-cols-[1.05fr_0.95fr]">
        <section className="hidden border-r border-slate-200 bg-indigo-950 p-8 text-white md:flex md:flex-col md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-white text-slate-950">
              <Sparkles className="size-5" />
            </div>
            <div>
              <p className="text-sm font-semibold">JobFit Agent</p>
              <p className="text-xs text-slate-400">Application intelligence workspace</p>
            </div>
          </div>
          <div className="space-y-5">
            <p className="max-w-sm text-3xl font-semibold leading-tight">
              Turn a job description into a scored application plan.
            </p>
            <div className="grid grid-cols-3 gap-3 text-xs text-slate-300">
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">Fit scoring</div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">Gap analysis</div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">Document generation</div>
            </div>
          </div>
        </section>
        <div className="p-8 md:p-10">
          <div className="mb-8 flex items-center gap-3 md:hidden">
            <div className="flex size-10 items-center justify-center rounded-lg bg-indigo-950 text-white">
              <Sparkles className="size-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-950">JobFit Agent</p>
              <p className="text-xs text-slate-500">Application workspace</p>
            </div>
          </div>
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
              <LockKeyhole className="size-3.5" />
              Secure workspace
            </div>
            <h1 className="text-2xl font-bold text-slate-950">Sign in</h1>
            <p className="mt-1 text-sm text-slate-500">Use your account email to continue.</p>
          </div>
          <div className="mt-6 space-y-6">
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
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm shadow-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-300"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-950 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-900 disabled:opacity-50"
              >
                {loading ? "Signing in..." : "Sign in"}
                {!loading && <ArrowRight className="size-4" />}
              </button>
            </form>
            <div className="flex items-center justify-between gap-3 text-xs">
              <Link to="/forgot-password" className="font-medium text-slate-600 hover:text-slate-950">Forgot password?</Link>
              <span className="text-slate-400">
                Have an invite?{" "}
                <Link to="/register" className="font-medium text-slate-700 hover:text-slate-950">Register</Link>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
