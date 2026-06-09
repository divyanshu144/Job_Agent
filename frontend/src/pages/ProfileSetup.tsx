import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type {
  ProfileResponse,
  ProfileReviewData,
  ProfileReviewLink,
  ProfileReviewProject,
  ProfileReviewResponse,
} from "../types";

const emptyReviewData = (): ProfileReviewData => ({
  target_role: "",
  key_skills: [],
  projects: [],
  experience: [],
  links: [],
  work_preferences: {
    locations: [],
    remote: "",
    role_types: [],
    industries: [],
  },
});

const emptyProject = (): ProfileReviewProject => ({
  name: "",
  description: "",
  highlights: [],
});

const emptyLink = (): ProfileReviewLink => ({
  label: "",
  url: "",
});

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function parseReviewData(raw: string | undefined): ProfileReviewData {
  if (!raw) return emptyReviewData();
  try {
    return { ...emptyReviewData(), ...JSON.parse(raw) } as ProfileReviewData;
  } catch {
    return emptyReviewData();
  }
}

function reviewFromProfile(profile: ProfileResponse): ProfileReviewResponse {
  return {
    profile_id: profile.id,
    review_data: parseReviewData(profile.profile_review_data),
    review_status: profile.review_status ?? "draft",
    reviewed_at: profile.reviewed_at ?? null,
    has_cv_text: Boolean(profile.cv_text.trim()),
  };
}

function ListEditor({
  label,
  values,
  placeholder,
  onChange,
}: {
  label: string;
  values: string[];
  placeholder?: string;
  onChange: (values: string[]) => void;
}) {
  const items = values.length ? values : [""];

  const update = (index: number, value: string) => {
    const next = [...items];
    next[index] = value;
    onChange(next);
  };

  const remove = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      {items.map((value, index) => (
        <div key={index} className="flex gap-2">
          <input
            value={value}
            onChange={(e) => update(index, e.target.value)}
            placeholder={placeholder}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
          />
          <button
            type="button"
            onClick={() => remove(index)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...items, ""])}
        className="text-sm font-medium text-blue-600 hover:text-blue-700"
      >
        Add {label.toLowerCase()}
      </button>
    </div>
  );
}

function ResumeUpload({
  uploading,
  disabled,
  onUpload,
}: {
  uploading: boolean;
  disabled: boolean;
  onUpload: (file: File) => Promise<void>;
}) {
  const fileRef = useRef<HTMLInputElement>(null);

  const handleChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    await onUpload(file);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="rounded-xl border-2 border-dashed border-slate-300 bg-white p-5 text-center space-y-3">
      <div>
        <p className="text-sm font-medium text-slate-800">Upload resume</p>
        <p className="text-xs text-slate-500">PDF or DOCX</p>
      </div>
      <label
        className={`inline-flex cursor-pointer rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
          uploading || disabled
            ? "bg-slate-200 text-slate-400"
            : "bg-slate-900 text-white hover:bg-slate-700"
        }`}
      >
        {uploading ? "Uploading..." : "Choose File"}
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="hidden"
          onChange={handleChange}
          disabled={uploading || disabled}
        />
      </label>
    </div>
  );
}

function AdminProfileTools() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  const loadProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      setProfile(await api.getProfile());
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setProfile(await api.refreshProfile());
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const upload = async (file: File) => {
    setUploading(true);
    setError(null);
    setUploadSuccess(false);
    try {
      setProfile(await api.uploadCv(file));
      setUploadSuccess(true);
      window.setTimeout(() => setUploadSuccess(false), 3000);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setUploading(false);
    }
  };

  const busy = loading || uploading;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Candidate Profile</h1>
          <p className="mt-1 text-sm text-slate-500">
            Admin profile tools remain available here.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={busy}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh Profile"}
        </button>
      </div>

      <ResumeUpload uploading={uploading} disabled={loading} onUpload={upload} />
      {uploadSuccess && <p className="text-sm font-medium text-green-600">Resume uploaded.</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {profile && (
        <>
          {profile.warnings.length > 0 && (
            <div className="space-y-1">
              {profile.warnings.map((warning, index) => (
                <p key={index} className="text-xs italic text-slate-500">
                  {warning}
                </p>
              ))}
            </div>
          )}

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">YAML Profile</h2>
            <pre className="max-h-64 overflow-auto rounded border bg-slate-50 p-3 text-xs">
              {profile.yaml_data}
            </pre>
          </section>

          {profile.cv_text && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                CV Text Preview
              </h2>
              <p className="whitespace-pre-wrap text-sm text-slate-600">
                {profile.cv_text.slice(0, 500)}...
              </p>
            </section>
          )}

          <p className="text-xs text-slate-400">
            Last refreshed: {new Date(profile.last_refreshed_at).toLocaleString()}
          </p>
        </>
      )}
    </div>
  );
}

export function ProfileSetup() {
  const { user } = useAuth();
  const [review, setReview] = useState<ProfileReviewResponse | null>(null);
  const [form, setForm] = useState<ProfileReviewData>(emptyReviewData);
  const [resumePreview, setResumePreview] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadReview = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getProfileReview();
      setReview(data);
      setForm(data.review_data);
      if (data.has_cv_text) {
        const profile = await api.getProfile();
        setResumePreview(profile.cv_text);
      }
    } catch (error) {
      try {
        const profile = await api.getProfile();
        const fallbackReview = reviewFromProfile(profile);
        setReview(fallbackReview);
        setForm(fallbackReview.review_data);
        setResumePreview(profile.cv_text);
        if (!fallbackReview.has_cv_text) {
          setError(errorMessage(error));
        }
      } catch {
        setError(errorMessage(error));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user?.is_admin) loadReview();
  }, [user?.is_admin]);

  if (user?.is_admin) {
    return <AdminProfileTools />;
  }

  const setField = <K extends keyof ProfileReviewData>(key: K, value: ProfileReviewData[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const setPreferences = <K extends keyof ProfileReviewData["work_preferences"]>(
    key: K,
    value: ProfileReviewData["work_preferences"][K],
  ) => {
    setForm((current) => ({
      ...current,
      work_preferences: { ...current.work_preferences, [key]: value },
    }));
  };

  const updateProject = (
    index: number,
    updater: (project: ProfileReviewProject) => ProfileReviewProject,
  ) => {
    setField(
      "projects",
      form.projects.map((project, i) => (i === index ? updater(project) : project)),
    );
  };

  const updateLink = (index: number, updater: (link: ProfileReviewLink) => ProfileReviewLink) => {
    setField("links", form.links.map((link, i) => (i === index ? updater(link) : link)));
  };

  const upload = async (file: File) => {
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const uploadedProfile = await api.uploadCv(file);
      const uploadedReview = reviewFromProfile(uploadedProfile);
      setReview(uploadedReview);
      setForm(uploadedReview.review_data);
      setResumePreview(uploadedProfile.cv_text);
      setSuccess("Resume uploaded.");
      try {
        const data = await api.getProfileReview();
        setReview(data);
        setForm(data.review_data);
      } catch {
        // The upload response already confirms the resume is stored; keep the UI usable.
      }
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setUploading(false);
    }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.saveProfileReview(form);
      setReview(data);
      setForm(data.review_data);
      setSuccess("Profile review saved.");
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const busy = loading || saving || uploading;

  return (
    <div className="mx-auto max-w-6xl p-6 space-y-6">
      <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-start">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Profile Review</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload a resume, then adjust the profile details used for job analysis.
          </p>
        </div>
        <Link
          to="/analyse"
          className="shrink-0 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
        >
          Continue to job analysis
        </Link>
      </div>

      {loading && <p className="text-sm text-slate-500">Loading profile...</p>}
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      {success && (
        <p className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
          {success}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-12">
        <div className="rounded-lg border border-slate-200 bg-white p-4 lg:col-span-5">
          <p className="text-xs font-semibold uppercase text-slate-500">Resume status</p>
          <p className="mt-2 text-sm font-medium text-slate-900">
            {review?.has_cv_text ? "Resume uploaded" : "No resume uploaded yet"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Resume upload alone is enough to run analysis.
          </p>
          {resumePreview.trim() && (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs font-medium text-blue-600">
                View extracted resume text
              </summary>
              <p className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                {resumePreview.slice(0, 1200)}
                {resumePreview.length > 1200 ? "..." : ""}
              </p>
            </details>
          )}
        </div>
        <div className="lg:col-span-3">
          <ResumeUpload uploading={uploading} disabled={loading || saving} onUpload={upload} />
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600 lg:col-span-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Review status</p>
          <p className="mt-2 font-medium text-slate-900">{review?.review_status ?? "draft"}</p>
          {review?.reviewed_at ? (
            <p className="mt-1 text-xs text-slate-500">
              Saved {new Date(review.reviewed_at).toLocaleString()}
            </p>
          ) : (
            <p className="mt-1 text-xs text-slate-500">Not saved yet</p>
          )}
        </div>
      </div>

      <form onSubmit={save} className="grid gap-4 lg:grid-cols-12">
        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-4 lg:col-span-5">
          <h2 className="text-lg font-semibold text-slate-900">Role and Skills</h2>
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Target role</label>
            <input
              value={form.target_role}
              onChange={(e) => setField("target_role", e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
              placeholder="Senior Backend Engineer"
            />
          </div>
          <ListEditor
            label="Skills"
            values={form.key_skills}
            placeholder="Python"
            onChange={(values) => setField("key_skills", values)}
          />
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-4 lg:col-span-7">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Projects</h2>
            <button
              type="button"
              onClick={() => setField("projects", [...form.projects, emptyProject()])}
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Add project
            </button>
          </div>
          {form.projects.length === 0 && <p className="text-sm text-slate-400">No projects added.</p>}
          {form.projects.map((project, index) => (
            <div key={index} className="space-y-3 border-t border-slate-200 pt-4 first:border-t-0 first:pt-0">
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => setField("projects", form.projects.filter((_, i) => i !== index))}
                  className="text-sm text-slate-500 hover:text-slate-800"
                >
                  Remove
                </button>
              </div>
              <input
                value={project.name}
                onChange={(e) => updateProject(index, (p) => ({ ...p, name: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Project name"
              />
              <textarea
                value={project.description}
                onChange={(e) =>
                  updateProject(index, (p) => ({ ...p, description: e.target.value }))
                }
                className="min-h-20 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Short description"
              />
              <ListEditor
                label="Highlights"
                values={project.highlights}
                placeholder="Improved matching quality"
                onChange={(values) => updateProject(index, (p) => ({ ...p, highlights: values }))}
              />
            </div>
          ))}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-4 lg:col-span-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Links</h2>
            <button
              type="button"
              onClick={() => setField("links", [...form.links, emptyLink()])}
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Add link
            </button>
          </div>
          {form.links.length === 0 && <p className="text-sm text-slate-400">No links added.</p>}
          {form.links.map((link, index) => (
            <div key={index} className="grid gap-2 md:grid-cols-[1fr_2fr_auto]">
              <input
                value={link.label}
                onChange={(e) => updateLink(index, (item) => ({ ...item, label: e.target.value }))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Label"
              />
              <input
                value={link.url}
                onChange={(e) => updateLink(index, (item) => ({ ...item, url: e.target.value }))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="https://..."
              />
              <button
                type="button"
                onClick={() => setField("links", form.links.filter((_, i) => i !== index))}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Remove
              </button>
            </div>
          ))}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 space-y-4 lg:col-span-7">
          <h2 className="text-lg font-semibold text-slate-900">Work Preferences</h2>
          <ListEditor
            label="Locations"
            values={form.work_preferences.locations}
            placeholder="London"
            onChange={(values) => setPreferences("locations", values)}
          />
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Remote preference</label>
            <input
              value={form.work_preferences.remote ?? ""}
              onChange={(e) => setPreferences("remote", e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
              placeholder="Remote, hybrid, onsite"
            />
          </div>
          <ListEditor
            label="Role types"
            values={form.work_preferences.role_types}
            placeholder="Full-time"
            onChange={(values) => setPreferences("role_types", values)}
          />
          <ListEditor
            label="Industries"
            values={form.work_preferences.industries}
            placeholder="Developer tools"
            onChange={(values) => setPreferences("industries", values)}
          />
        </section>

        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-4 lg:col-span-12">
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save profile"}
          </button>
          <Link
            to="/analyse"
            className="rounded-lg border border-slate-300 px-5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Continue to job analysis
          </Link>
        </div>
      </form>
    </div>
  );
}
