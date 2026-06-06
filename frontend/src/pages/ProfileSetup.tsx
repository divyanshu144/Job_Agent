import { useRef, useState, useEffect } from "react";
import { api } from "../api/client";
import type { ProfileResponse } from "../types";

export function ProfileSetup() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadProfile = async () => {
    setLoading(true); setError(null);
    try {
      setProfile(await api.getProfile());
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
      setProfile(await api.refreshProfile());
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const handleCvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(null); setUploadSuccess(false);
    try {
      setProfile(await api.uploadCv(file));
      setUploadSuccess(true);
      setTimeout(() => setUploadSuccess(false), 3000);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const busy = loading || uploading;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-slate-900">Candidate Profile</h1>
        <button onClick={refresh} disabled={busy} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
          {loading ? "Refreshing…" : "Refresh Profile"}
        </button>
      </div>

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
          </p>
        </>
      )}
    </div>
  );
}
