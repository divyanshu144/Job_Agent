import { useRef, useState, useEffect } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { ProfileResponse, ReferralEntry } from "../types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{title}</h2>
      {children}
    </div>
  );
}

export function ProfileSetup() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Referral state
  const [referrals, setReferrals] = useState<ReferralEntry[]>([]);
  const [referralsCopied, setReferralsCopied] = useState(false);

  // Invite state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviteExpiry, setInviteExpiry] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await api.getProfile();
      setProfile(p);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
    api.getReferrals().then(setReferrals).catch(() => {});
  }, []);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await api.refreshProfile();
      setProfile(p);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleCvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setUploadSuccess(false);
    try {
      const p = await api.uploadCv(file);
      setProfile(p);
      setUploadSuccess(true);
      setTimeout(() => setUploadSuccess(false), 3000);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleGenerateInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteLoading(true);
    setInviteError(null);
    setInviteLink(null);
    try {
      const res = await api.createInvite(inviteEmail || undefined);
      const fullUrl = `${window.location.origin}${res.invite_url}`;
      setInviteLink(fullUrl);
      setInviteExpiry(new Date(res.expires_at).toLocaleString());
      setInviteEmail("");
    } catch (e) {
      setInviteError(String(e));
    } finally {
      setInviteLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!inviteLink) return;
    await navigator.clipboard.writeText(inviteLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyReferral = async () => {
    if (!user?.referral_code) return;
    const link = `${window.location.origin}/register?ref=${user.referral_code}`;
    await navigator.clipboard.writeText(link);
    setReferralsCopied(true);
    setTimeout(() => setReferralsCopied(false), 2000);
  };

  const busy = loading || uploading;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-5">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Profile</h1>
          <p className="text-sm text-slate-500 mt-0.5">{user?.email}</p>
        </div>
        <button
          onClick={refresh}
          disabled={busy}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Refreshing…" : "Refresh Profile"}
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
      )}

      {/* Health summary */}
      {profile && (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
            <p className="text-xs text-slate-500 mb-1">CV</p>
            <p className={`text-sm font-semibold ${profile.cv_text ? "text-emerald-600" : "text-slate-400"}`}>
              {profile.cv_text ? "Uploaded" : "Not uploaded"}
            </p>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
            <p className="text-xs text-slate-500 mb-1">Last refresh</p>
            <p className="text-sm font-semibold text-slate-800">
              {new Date(profile.last_refreshed_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      )}

      {/* CV Upload */}
      <Section title="CV">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-700">
              {profile?.cv_text ? "CV uploaded — upload a new PDF to replace it." : "No CV uploaded yet."}
            </p>
            <p className="text-xs text-slate-400 mt-0.5">Replaces the existing CV and rebuilds your profile</p>
          </div>
          <label className={`shrink-0 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "bg-slate-100 text-slate-400" : "bg-slate-900 text-white hover:bg-slate-700"}`}>
            {uploading ? "Uploading…" : "Upload PDF"}
            <input ref={fileRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={handleCvUpload} disabled={busy} />
          </label>
        </div>
        {uploadSuccess && (
          <p className="text-emerald-600 text-sm font-medium">CV uploaded and profile rebuilt.</p>
        )}
      </Section>

      {/* YAML preview */}
      {profile && (
        <Section title="YAML Profile">
          <pre className="text-xs bg-slate-50 p-3 rounded-lg border border-slate-200 overflow-auto max-h-64 text-slate-700">{profile.yaml_data}</pre>
          <p className="text-xs text-slate-400">
            Edit <code className="bg-slate-100 px-1 rounded">candidate_profile.yaml</code> on disk, then click Refresh Profile.
          </p>
        </Section>
      )}

      {/* CV text preview */}
      {profile?.cv_text && (
        <Section title="CV Preview">
          <p className="text-sm text-slate-600 whitespace-pre-wrap leading-relaxed">{profile.cv_text.slice(0, 600)}…</p>
        </Section>
      )}

      {/* Referral link */}
      {user?.referral_code && (
        <Section title="Referral Link">
          <p className="text-sm text-slate-600">
            Share this link to invite people. Anyone who registers with it is tracked as your referral.
          </p>
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
            <p className="flex-1 text-xs font-mono text-slate-700 truncate">
              {window.location.origin}/register?ref={user.referral_code}
            </p>
            <button
              onClick={handleCopyReferral}
              className="shrink-0 px-2.5 py-1 rounded-md bg-slate-200 text-slate-700 text-xs font-medium hover:bg-slate-300 transition-colors"
            >
              {referralsCopied ? "Copied!" : "Copy"}
            </button>
          </div>
          {referrals.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs font-medium text-slate-500">
                {referrals.length} {referrals.length === 1 ? "person" : "people"} joined via your link
              </p>
              <div className="rounded-lg border border-slate-200 overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Email</th>
                      <th className="text-left px-3 py-2 font-medium">Joined</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {referrals.map((r) => (
                      <tr key={r.id} className="bg-white">
                        <td className="px-3 py-2 text-slate-700">{r.email}</td>
                        <td className="px-3 py-2 text-slate-500">{new Date(r.joined_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-400">No one has joined via your link yet.</p>
          )}
        </Section>
      )}

      {/* Invite (admin only) */}
      {user?.is_admin && (
        <Section title="Invite a User">
          <p className="text-sm text-slate-600">
            Generate a one-time invite link (valid 72 hours). Share it with anyone you want to give access.
          </p>
          <form onSubmit={handleGenerateInvite} className="flex gap-2">
            <input
              type="email"
              placeholder="Email (optional — locks invite to one address)"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <button
              type="submit"
              disabled={inviteLoading}
              className="shrink-0 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {inviteLoading ? "Generating…" : "Generate Link"}
            </button>
          </form>
          {inviteError && (
            <p className="text-sm text-red-600">{inviteError}</p>
          )}
          {inviteLink && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                <p className="flex-1 text-xs font-mono text-slate-700 break-all">{inviteLink}</p>
                <button
                  onClick={handleCopy}
                  className="shrink-0 px-2.5 py-1 rounded-md bg-slate-200 text-slate-700 text-xs font-medium hover:bg-slate-300 transition-colors"
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
              </div>
              <p className="text-xs text-slate-400">Expires {inviteExpiry}</p>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
