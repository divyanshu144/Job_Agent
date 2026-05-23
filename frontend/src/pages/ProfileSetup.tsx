import { useRef, useState, useEffect } from "react";
import { api } from "../api/client";
import type { ProfileResponse, ProfileStatusResponse } from "../types";

function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

export function ProfileSetup() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [status, setStatus] = useState<ProfileStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [githubRefreshing, setGithubRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadProfile = async () => {
    setLoading(true); setError(null);
    try {
      const [p, s] = await Promise.all([api.getProfile(), api.getProfileStatus()]);
      setProfile(p); setStatus(s);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadProfile(); }, []);

  const refresh = async () => {
    setLoading(true); setError(null);
    try {
      const p = await api.refreshProfile();
      const s = await api.getProfileStatus();
      setProfile(p); setStatus(s);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const refreshGithub = async () => {
    setGithubRefreshing(true); setError(null);
    try {
      const r = await api.refreshGithub();
      setProfile(r.profile);
      const s = await api.getProfileStatus();
      setStatus(s);
    } catch (e) { setError(String(e)); }
    finally { setGithubRefreshing(false); }
  };

  const handleCvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(null); setUploadSuccess(false);
    try {
      const p = await api.uploadCv(file);
      const s = await api.getProfileStatus();
      setProfile(p); setStatus(s);
      setUploadSuccess(true);
      setTimeout(() => setUploadSuccess(false), 3000);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const busy = loading || uploading || githubRefreshing;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-slate-900">Candidate Profile</h1>
        <button onClick={refresh} disabled={busy} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
          {loading ? "Refreshing…" : "Refresh Profile"}
        </button>
      </div>

      {/* GitHub staleness banner */}
      {status?.github_is_stale && (
        <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-800">
            {status.github_last_fetched_at
              ? `GitHub data last synced ${daysSince(status.github_last_fetched_at)} day(s) ago`
              : "GitHub data not yet synced"}
          </p>
          <button
            onClick={refreshGithub}
            disabled={busy}
            className="ml-4 shrink-0 px-3 py-1 rounded-md bg-amber-600 text-white text-xs font-medium hover:bg-amber-700 disabled:opacity-50"
          >
            {githubRefreshing ? "Syncing…" : "Refresh GitHub"}
          </button>
        </div>
      )}

      {/* CV Upload */}
      <div className="border-2 border-dashed border-slate-300 rounded-xl p-5 flex flex-col items-center gap-3 text-center">
        <p className="text-sm font-medium text-slate-700">Upload your CV (PDF)</p>
        <p className="text-xs text-slate-400">Replaces the existing CV and rebuilds your profile</p>
        <label className={`px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "bg-slate-200 text-slate-400" : "bg-slate-900 text-white hover:bg-slate-700"}`}>
          {uploading ? "Uploading…" : "Choose PDF"}
          <input ref={fileRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={handleCvUpload} disabled={busy} />
        </label>
        {uploadSuccess && <p className="text-green-600 text-sm font-medium">CV uploaded and profile rebuilt!</p>}
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {profile && (
        <>
          {/* Inline warnings */}
          {profile.warnings.length > 0 && (
            <div className="space-y-1">
              {profile.warnings.map((w, i) => (
                <p key={i} className="text-xs text-slate-500 italic">{w}</p>
              ))}
            </div>
          )}

          <div>
            <h2 className="text-xs font-semibold text-slate-500 uppercase mb-2">YAML Profile</h2>
            <pre className="text-xs bg-slate-50 p-3 rounded border overflow-auto max-h-64">{profile.yaml_data}</pre>
          </div>
          {profile.cv_text && (
            <div>
              <h2 className="text-xs font-semibold text-slate-500 uppercase mb-2">CV Text (preview)</h2>
              <p className="text-sm text-slate-600 whitespace-pre-wrap">{profile.cv_text.slice(0, 500)}…</p>
            </div>
          )}
          <p className="text-xs text-slate-400">
            Last refreshed: {new Date(profile.last_refreshed_at).toLocaleString()}
            {profile.github_last_fetched_at && (
              <> · GitHub synced: {new Date(profile.github_last_fetched_at).toLocaleString()}</>
            )}
          </p>
        </>
      )}
    </div>
  );
}
