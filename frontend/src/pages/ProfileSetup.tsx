import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, FileUp, FolderGit2, Link2, MapPin, RefreshCw, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { api, errorMessage } from "../api/client";
import { PageHeader, PageShell, Panel, PrimaryButton, SectionHeader, StatusPill } from "../components/portal";
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
      <label className="text-sm font-medium text-zinc-700">{label}</label>
      {items.map((value, index) => (
        <div key={index} className="flex flex-col gap-2 sm:flex-row">
          <input
            value={value}
            onChange={(e) => update(index, e.target.value)}
            placeholder={placeholder}
            className="min-w-0 flex-1 rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-sm text-zinc-950 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
          />
          <button
            type="button"
            onClick={() => remove(index)}
            className="rounded-xl border border-zinc-200 px-3 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50"
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...items, ""])}
        className="text-sm font-medium text-blue-700 hover:text-blue-600"
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
    <div className="rounded-2xl border border-dashed border-zinc-200 bg-white p-6 text-center shadow-sm">
      <div className="mx-auto flex size-11 items-center justify-center rounded-xl bg-blue-50 text-blue-700 shadow-sm">
        <FileUp className="size-5" />
      </div>
      <div className="mt-3">
        <p className="text-sm font-semibold text-zinc-950">Upload resume</p>
        <p className="mt-1 text-xs text-zinc-500">PDF or DOCX</p>
      </div>
      <div className="mt-4">
        <label
          className={`inline-flex cursor-pointer rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
            uploading || disabled
              ? "bg-zinc-200 text-zinc-400"
              : "bg-blue-600 text-white hover:bg-blue-500"
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
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
        <div className="grid gap-0 lg:grid-cols-[1fr_360px]">
          <div className="space-y-6 p-6 md:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="mb-3 inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                  <ShieldCheck className="size-3.5" />
                  Profile readiness
                </div>
                <h1 className="text-2xl font-bold text-slate-950 md:text-3xl">Candidate Profile</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  Maintain the shared candidate profile and resume source used by admin workflows.
                </p>
              </div>
              <button
                onClick={refresh}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
              >
                <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
                {loading ? "Refreshing..." : "Refresh profile"}
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                <p className="text-xs font-medium text-emerald-700">Profile status</p>
                <p className="mt-2 text-sm font-semibold text-emerald-950">{profile ? "Loaded" : "Waiting"}</p>
              </div>
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <p className="text-xs font-medium text-blue-700">Resume text</p>
                <p className="mt-2 text-sm font-semibold text-blue-950">{profile?.cv_text ? "Available" : "Missing"}</p>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-xs font-medium text-amber-700">Last refresh</p>
                <p className="mt-2 truncate text-sm font-semibold text-amber-950">
                  {profile ? new Date(profile.last_refreshed_at).toLocaleDateString() : "Not yet"}
                </p>
              </div>
            </div>
          </div>

          <aside className="border-t border-zinc-200 bg-zinc-50 p-6 text-zinc-950 lg:border-l lg:border-t-0 md:p-8">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-zinc-950 text-white shadow-sm">
                <UserRound className="size-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-zinc-950">Resume source</p>
                <p className="text-xs text-zinc-500">Used for matching and package preparation</p>
              </div>
            </div>
            <div className="mt-6 rounded-2xl border border-zinc-200 bg-white p-4">
              <ResumeUpload uploading={uploading} disabled={loading} onUpload={upload} />
            </div>
          </aside>
        </div>
      </section>

      {uploadSuccess && (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
          Resume uploaded.
        </p>
      )}
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      {profile && (
        <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          {profile.warnings.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 lg:col-span-2">
              {profile.warnings.map((warning, index) => (
                <p key={index} className="text-xs font-medium text-amber-800">
                  {warning}
                </p>
              ))}
            </div>
          )}

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="size-4 text-blue-600" />
              <h2 className="text-sm font-semibold text-slate-800">YAML Profile</h2>
            </div>
            <pre className="max-h-72 overflow-auto rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs leading-5 text-zinc-700">
              {profile.yaml_data}
            </pre>
          </div>

          {profile.cv_text && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <FileUp className="size-4 text-emerald-600" />
                <h2 className="text-sm font-semibold text-slate-800">CV Text Preview</h2>
              </div>
              <p className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-emerald-100 bg-emerald-50/40 p-4 text-sm leading-6 text-slate-700">
                {profile.cv_text.slice(0, 500)}...
              </p>
            </div>
          )}

          <p className="text-xs text-slate-400 lg:col-span-2">
            Last refreshed: {new Date(profile.last_refreshed_at).toLocaleString()}
          </p>
        </section>
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
  const clean = (values: string[]) => values.filter((value) => value.trim());
  const readinessItems = [
    { label: "Resume uploaded", ready: Boolean(review?.has_cv_text), detail: "Used to prepare tailored packages" },
    { label: "Target role", ready: Boolean(form.target_role.trim()), detail: form.target_role || "Add the roles you want" },
    { label: "Skills added", ready: clean(form.key_skills).length > 0, detail: `${clean(form.key_skills).length} listed` },
    { label: "Projects added", ready: form.projects.some((project) => project.name.trim() || project.description.trim()), detail: `${form.projects.length} project${form.projects.length === 1 ? "" : "s"}` },
  ];
  const completeCount = readinessItems.filter((item) => item.ready).length;

  return (
    <PageShell>
      <PageHeader
        title="Profile readiness"
        description="Keep your background, target roles, projects, and preferences current so each application package can be tailored accurately."
        actions={
          <Link
            to="/analyse"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
          >
            Submit a role
          </Link>
        }
      />

      {loading && <p className="text-sm text-zinc-500">Loading profile...</p>}
      {error && <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      {success && (
        <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {success}
        </p>
      )}

      <section className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Panel>
          <SectionHeader
            title="Readiness checklist"
            description={`${completeCount} of ${readinessItems.length} essentials complete`}
            action={<StatusPill tone={completeCount === readinessItems.length ? "success" : "warning"}>{review?.review_status ?? "draft"}</StatusPill>}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            {readinessItems.map((item) => (
              <div key={item.label} className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className={`mt-0.5 size-5 ${item.ready ? "text-emerald-600" : "text-zinc-300"}`} />
                  <div>
                    <p className="text-sm font-semibold text-zinc-950">{item.label}</p>
                    <p className="mt-1 text-xs leading-5 text-zinc-500">{item.detail}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel>
          <SectionHeader title="Resume" description={review?.has_cv_text ? "Resume is ready for package preparation" : "Upload a resume to improve tailoring"} />
          <ResumeUpload uploading={uploading} disabled={loading || saving} onUpload={upload} />
          {resumePreview.trim() && (
            <details className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
              <summary className="cursor-pointer text-sm font-medium text-blue-700">
                Preview saved resume text
              </summary>
              <p className="mt-3 max-h-36 overflow-auto whitespace-pre-wrap rounded-xl bg-white p-3 text-xs leading-5 text-zinc-600">
                {resumePreview.slice(0, 1200)}
                {resumePreview.length > 1200 ? "..." : ""}
              </p>
            </details>
          )}
          {review?.reviewed_at && (
            <p className="mt-4 text-xs text-zinc-500">
              Last saved {new Date(review.reviewed_at).toLocaleString()}
            </p>
          )}
        </Panel>
      </section>

      <form onSubmit={save} className="grid gap-4 lg:grid-cols-12">
        <Panel className="space-y-4 lg:col-span-5">
          <SectionHeader title="Target roles and skills" description="Tell JobFit what opportunities should be prioritised." />
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">Target role</label>
            <input
              value={form.target_role}
              onChange={(e) => setField("target_role", e.target.value)}
              className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
              placeholder="Senior Backend Engineer"
            />
          </div>
          <ListEditor
            label="Skills"
            values={form.key_skills}
            placeholder="Python"
            onChange={(values) => setField("key_skills", values)}
          />
        </Panel>

        <Panel className="space-y-4 lg:col-span-7">
          <div className="flex flex-col items-start justify-between gap-2 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <FolderGit2 className="size-4 text-zinc-500" />
              <h2 className="text-lg font-semibold text-zinc-950">Projects</h2>
            </div>
            <button
              type="button"
              onClick={() => setField("projects", [...form.projects, emptyProject()])}
              className="text-sm font-medium text-blue-700 hover:text-blue-600"
            >
              Add project
            </button>
          </div>
          {form.projects.length === 0 && <p className="text-sm text-zinc-400">No projects added.</p>}
          {form.projects.map((project, index) => (
            <div key={index} className="space-y-3 border-t border-zinc-200 pt-4 first:border-t-0 first:pt-0">
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => setField("projects", form.projects.filter((_, i) => i !== index))}
                  className="text-sm text-zinc-500 hover:text-zinc-800"
                >
                  Remove
                </button>
              </div>
              <input
                value={project.name}
                onChange={(e) => updateProject(index, (p) => ({ ...p, name: e.target.value }))}
                className="w-full rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                placeholder="Project name"
              />
              <textarea
                value={project.description}
                onChange={(e) =>
                  updateProject(index, (p) => ({ ...p, description: e.target.value }))
                }
                className="min-h-20 w-full rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
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
        </Panel>

        <Panel className="space-y-4 lg:col-span-5">
          <div className="flex flex-col items-start justify-between gap-2 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <Link2 className="size-4 text-zinc-500" />
              <h2 className="text-lg font-semibold text-zinc-950">Links</h2>
            </div>
            <button
              type="button"
              onClick={() => setField("links", [...form.links, emptyLink()])}
              className="text-sm font-medium text-blue-700 hover:text-blue-600"
            >
              Add link
            </button>
          </div>
          {form.links.length === 0 && <p className="text-sm text-zinc-400">No links added.</p>}
          {form.links.map((link, index) => (
            <div key={index} className="grid gap-2 md:grid-cols-[1fr_2fr_auto]">
              <input
                value={link.label}
                onChange={(e) => updateLink(index, (item) => ({ ...item, label: e.target.value }))}
                className="rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                placeholder="Label"
              />
              <input
                value={link.url}
                onChange={(e) => updateLink(index, (item) => ({ ...item, url: e.target.value }))}
                className="rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                placeholder="https://..."
              />
              <button
                type="button"
                onClick={() => setField("links", form.links.filter((_, i) => i !== index))}
                className="rounded-xl border border-zinc-200 px-3 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50"
              >
                Remove
              </button>
            </div>
          ))}
        </Panel>

        <Panel className="space-y-4 lg:col-span-7">
          <div className="flex items-center gap-2">
            <MapPin className="size-4 text-zinc-500" />
            <h2 className="text-lg font-semibold text-zinc-950">Work preferences</h2>
          </div>
          <ListEditor
            label="Locations"
            values={form.work_preferences.locations}
            placeholder="London"
            onChange={(values) => setPreferences("locations", values)}
          />
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">Remote preference</label>
            <input
              value={form.work_preferences.remote ?? ""}
              onChange={(e) => setPreferences("remote", e.target.value)}
              className="w-full rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
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
        </Panel>

        <div className="flex flex-wrap items-center gap-3 rounded-3xl border border-zinc-200 bg-white p-4 shadow-sm lg:col-span-12">
          <PrimaryButton
            type="submit"
            disabled={busy}
          >
            {saving ? "Saving..." : "Save profile"}
          </PrimaryButton>
          <Link
            to="/analyse"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-50"
          >
            Continue to role review
          </Link>
        </div>
      </form>
    </PageShell>
  );
}
