import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Briefcase,
  FileText,
  FileUp,
  GraduationCap,
  Link2,
  Mail,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type {
  ProfileResponse,
  ProfileReviewData,
  ProfileReviewEducation,
  ProfileReviewLink,
  ProfileReviewResponse,
  ResumeIdentity,
  ResumeVersionSummary,
} from "../types";

const emptyReviewData = (): ProfileReviewData => ({
  target_role: "",
  target_roles: [],
  key_skills: [],
  projects: [],
  experience: [],
  education: [],
  links: [],
  work_preferences: { locations: [], remote: "", role_types: [], industries: [] },
});

const emptyLink = (): ProfileReviewLink => ({ label: "", url: "" });
const emptyEducation = (): ProfileReviewEducation => ({
  institution: "",
  degree: "",
  field_of_study: "",
  dates: "",
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

const CARD = "rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5";
const EYEBROW = "mb-3 font-mono text-[11px] uppercase tracking-[0.18em] text-[#a1a1aa]";
const INPUT =
  "w-full rounded-xl border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2.5 text-sm text-[#0f0f17] outline-none transition focus:border-[#5b5bd6] focus:ring-2 focus:ring-[rgba(91,91,214,0.15)]";
const PILL = "inline-flex items-center rounded-full bg-[#f0f0f4] px-2.5 py-1 text-xs font-medium text-[#52525b]";

function EditLink({ onClick, to }: { onClick?: () => void; to?: string }) {
  const cls =
    "inline-flex items-center gap-1 text-sm font-medium text-[#5b5bd6] transition-colors hover:text-[#4f4fc9]";
  if (to) return <Link to={to} className={cls}>Edit →</Link>;
  return (
    <button type="button" onClick={onClick} className={cls}>
      Edit →
    </button>
  );
}

function IconTile({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex size-10 items-center justify-center rounded-xl bg-[#ededf8] text-[#5b5bd6]">
      {children}
    </div>
  );
}

export function ProfileSetup() {
  const { user } = useAuth();
  const [review, setReview] = useState<ProfileReviewResponse | null>(null);
  const [form, setForm] = useState<ProfileReviewData>(emptyReviewData);
  const [identity, setIdentity] = useState<ResumeIdentity | null>(null);
  const [versions, setVersions] = useState<ResumeVersionSummary[]>([]);
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [skillDraft, setSkillDraft] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rev, prof] = await Promise.all([
        api.getProfileReview().catch(() => null),
        api.getProfile(),
      ]);
      const resolved = rev ?? reviewFromProfile(prof);
      setReview(resolved);
      setForm(resolved.review_data);
      // Best-effort extras — never block the page if they fail.
      void api.getProfileIdentity().then(setIdentity).catch(() => setIdentity(null));
      void api.listResumeVersions().then(setVersions).catch(() => setVersions([]));
      void api
        .getMasterResume()
        .then((d) => setSummary(d.content.summary ?? ""))
        .catch(() => setSummary(""));
    } catch (e) {
      setError(errorMessage(e, "Couldn't load your profile"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setField = <K extends keyof ProfileReviewData>(key: K, value: ProfileReviewData[K]) =>
    setForm((c) => ({ ...c, [key]: value }));

  const addSkill = (raw: string) => {
    const v = raw.trim();
    if (v && !form.key_skills.some((s) => s.toLowerCase() === v.toLowerCase())) {
      setField("key_skills", [...form.key_skills, v]);
    }
    setSkillDraft("");
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const p = await api.uploadCv(file);
      const r = reviewFromProfile(p);
      setReview(r);
      setForm(r.review_data);
      setSuccess("Resume uploaded and profile updated.");
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const saveDetails = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.saveProfileReview(form);
      setReview(data);
      setForm(data.review_data);
      setSuccess("Profile saved.");
      setEditing(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await api.refreshProfile();
      await load();
      setSuccess("Profile rebuilt from your source.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  };

  const completion = useMemo(() => {
    const checks = [
      Boolean(review?.has_cv_text),
      form.key_skills.length > 0,
      form.experience.length > 0,
      form.education.length > 0,
      Boolean(summary.trim() || form.target_role.trim()),
      form.links.some((l) => l.url.trim()),
    ];
    return Math.round((checks.filter(Boolean).length / checks.length) * 100);
  }, [review, form, summary]);

  const name = identity?.name?.trim() || user?.email?.split("@")[0] || "Your profile";
  const initials =
    name
      .split(/\s+/)
      .map((p) => p[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("")
      .toUpperCase() || "?";
  const email = identity?.email || user?.email || "";
  const contact = [identity?.location, email, identity?.phone].filter(Boolean).join("  ·  ");
  const roles = form.experience.length;
  const skills = form.key_skills.length;
  const wp = form.work_preferences;

  if (loading && !review) {
    return (
      <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-10 text-center text-sm text-[#71717a]">
        Loading your profile…
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-2.5 text-sm text-rose-600">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700">
          {success}
        </div>
      )}

      {/* ── Identity & documents ── */}
      <section>
        <p className={EYEBROW}>Identity &amp; documents</p>
        <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr_1fr]">
          {/* Identity */}
          <div className={CARD}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-[#0f0f17] text-sm font-semibold text-white">
                  {initials}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-base font-semibold text-[#0f0f17]">{name}</h3>
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                      <span className="size-1.5 rounded-full bg-emerald-500" /> Open to work
                    </span>
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                      {completion}% complete
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-[#71717a]">{contact || email}</p>
                </div>
              </div>
              <EditLink onClick={() => setEditing(true)} />
            </div>
          </div>

          {/* Resume */}
          <div className={CARD}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <IconTile>
                  <FileText className="size-5" />
                </IconTile>
                <div>
                  <h3 className="text-base font-semibold text-[#0f0f17]">Resume</h3>
                  <p className="mt-0.5 text-xs text-[#71717a]">
                    Edit the wording, or replace it from a file.
                  </p>
                </div>
              </div>
              <EditLink to="/resume" />
            </div>
          </div>

          {/* Cover letter */}
          <div className={CARD}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <IconTile>
                  <Mail className="size-5" />
                </IconTile>
                <div>
                  <h3 className="text-base font-semibold text-[#0f0f17]">Cover letter</h3>
                  <p className="mt-0.5 text-xs text-[#71717a]">
                    Drafted and tailored each time you prepare a package.
                  </p>
                </div>
              </div>
              <EditLink to="/analyse" />
            </div>
          </div>
        </div>
      </section>

      {/* ── Resume versions ── */}
      <section>
        <p className={EYEBROW}>
          Resume versions{" "}
          <span className="normal-case tracking-normal text-[#a1a1aa]">
            — each carries its own emphasis &amp; formatting
          </span>
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {versions.map((v) => (
            <Link
              key={v.id}
              to="/resume"
              className={`${CARD} block transition-shadow hover:shadow-[0_2px_10px_rgba(0,0,0,0.06)] ${
                v.is_active ? "ring-1 ring-[#5b5bd6]" : ""
              }`}
            >
              <div className="flex items-center justify-between">
                {v.is_active ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#5b5bd6]">
                    <span className="size-1.5 rounded-full bg-[#5b5bd6]" /> Active
                  </span>
                ) : (
                  <span className="text-[11px] text-[#a1a1aa]">
                    Updated {new Date(v.updated_at).toLocaleDateString()}
                  </span>
                )}
                <span className="rounded-md bg-[#f0f0f4] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#71717a]">
                  rev {v.rev}
                </span>
              </div>
              <h3 className="mt-3 text-sm font-semibold text-[#0f0f17]">{v.name}</h3>
              <p className="mt-0.5 text-xs text-[#71717a]">
                {roles} role{roles === 1 ? "" : "s"} · {skills} skill{skills === 1 ? "" : "s"}
              </p>
            </Link>
          ))}
          <Link
            to="/resume"
            className="flex flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-[rgba(91,91,214,0.3)] bg-[rgba(91,91,214,0.03)] p-5 text-center transition-colors hover:bg-[rgba(91,91,214,0.06)]"
          >
            <Plus className="size-5 text-[#5b5bd6]" />
            <span className="text-sm font-medium text-[#0f0f17]">New version</span>
            <span className="text-xs text-[#71717a]">Duplicate this one or start fresh</span>
          </Link>
        </div>
      </section>

      {/* ── Profile details ── */}
      <section>
        <p className={EYEBROW}>Profile details</p>
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          {/* Left column */}
          <div className="space-y-4">
            {/* Summary */}
            <div className={CARD}>
              <div className="mb-2 flex items-start justify-between gap-3">
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#a1a1aa]">
                  Professional summary
                </p>
                <EditLink to="/resume" />
              </div>
              {summary.trim() ? (
                <p className="text-sm leading-6 text-[#3f3f46]">{summary}</p>
              ) : (
                <p className="text-sm italic text-[#a1a1aa]">
                  Add a professional summary — the first thing recruiters read.
                </p>
              )}
            </div>

            {/* Education */}
            <div className={CARD}>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <IconTile>
                    <GraduationCap className="size-5" />
                  </IconTile>
                  <div>
                    <h3 className="text-base font-semibold text-[#0f0f17]">Education</h3>
                    <p className="text-xs text-[#71717a]">
                      {form.education.length} entr{form.education.length === 1 ? "y" : "ies"}
                    </p>
                  </div>
                </div>
                <EditLink onClick={() => setEditing(true)} />
              </div>
              {form.education.length === 0 ? (
                <p className="text-sm italic text-[#a1a1aa]">No education added yet.</p>
              ) : (
                <div className="space-y-4">
                  {form.education.map((ed, i) => (
                    <div key={i} className="border-l-2 border-[rgba(0,0,0,0.08)] pl-4">
                      <p className="text-sm font-semibold text-[#0f0f17]">{ed.institution}</p>
                      <p className="text-sm text-[#3f3f46]">
                        {[ed.degree, ed.field_of_study].filter(Boolean).join(" · ")}
                      </p>
                      {ed.dates && <p className="mt-0.5 text-xs text-[#71717a]">{ed.dates}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Experience */}
            <div className={CARD}>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <IconTile>
                    <Briefcase className="size-5" />
                  </IconTile>
                  <div>
                    <h3 className="text-base font-semibold text-[#0f0f17]">Experience</h3>
                    <p className="text-xs text-[#71717a]">
                      {roles} role{roles === 1 ? "" : "s"}
                    </p>
                  </div>
                </div>
                <EditLink to="/resume" />
              </div>
              {roles === 0 ? (
                <p className="text-sm italic text-[#a1a1aa]">No experience added yet.</p>
              ) : (
                <div className="space-y-5">
                  {form.experience.map((exp, i) => (
                    <div key={i} className="border-l-2 border-[rgba(0,0,0,0.08)] pl-4">
                      <p className="text-sm font-semibold text-[#0f0f17]">{exp.role}</p>
                      <p className="text-sm text-[#3f3f46]">{exp.company}</p>
                      {exp.dates && <p className="mt-0.5 text-xs text-[#71717a]">{exp.dates}</p>}
                      {exp.highlights?.length > 0 && (
                        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm leading-6 text-[#3f3f46]">
                          {exp.highlights.slice(0, 3).map((h, j) => (
                            <li key={j}>{h}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right column — preferences */}
          <div className="space-y-4">
            <div className={CARD}>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <IconTile>
                    <Sparkles className="size-5" />
                  </IconTile>
                  <div>
                    <h3 className="text-base font-semibold text-[#0f0f17]">Preferences</h3>
                    <p className="text-xs text-[#71717a]">What we tailor every package toward.</p>
                  </div>
                </div>
                <EditLink onClick={() => setEditing(true)} />
              </div>

              <div className="space-y-4">
                <div>
                  <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.15em] text-[#a1a1aa]">
                    Target roles
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {[form.target_role, ...form.target_roles].filter(Boolean).length === 0 ? (
                      <span className="text-sm italic text-[#a1a1aa]">Not set</span>
                    ) : (
                      [...new Set([form.target_role, ...form.target_roles].filter(Boolean))].map(
                        (r) => (
                          <span key={r} className={PILL}>
                            {r}
                          </span>
                        ),
                      )
                    )}
                  </div>
                </div>

                <div>
                  <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.15em] text-[#a1a1aa]">
                    Work preferences
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {wp.remote && <span className={PILL}>{wp.remote}</span>}
                    {wp.locations.map((l) => (
                      <span key={l} className={PILL}>
                        <MapPin className="mr-1 size-3" />
                        {l}
                      </span>
                    ))}
                    {wp.role_types.map((r) => (
                      <span key={r} className={PILL}>
                        {r}
                      </span>
                    ))}
                    {wp.industries.map((r) => (
                      <span key={r} className={PILL}>
                        {r}
                      </span>
                    ))}
                    {!wp.remote &&
                      wp.locations.length === 0 &&
                      wp.role_types.length === 0 &&
                      wp.industries.length === 0 && (
                        <span className="text-sm italic text-[#a1a1aa]">Not set</span>
                      )}
                  </div>
                </div>

                <div>
                  <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.15em] text-[#a1a1aa]">
                    Skills{skills > 0 ? ` · ${skills}` : ""}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {skills === 0 ? (
                      <span className="text-sm italic text-[#a1a1aa]">Not set</span>
                    ) : (
                      form.key_skills.slice(0, 18).map((s) => (
                        <span key={s} className={PILL}>
                          {s}
                        </span>
                      ))
                    )}
                    {skills > 18 && <span className={PILL}>+{skills - 18} more</span>}
                  </div>
                </div>
              </div>
            </div>

            {/* Source / tools */}
            <div className={CARD}>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-[#0f0f17] px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28]">
                  <FileUp className="size-4" />
                  {uploading ? "Uploading…" : "Replace resume"}
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    className="hidden"
                    onChange={upload}
                    disabled={uploading}
                  />
                </label>
                {user?.is_admin && (
                  <button
                    type="button"
                    onClick={() => void refresh()}
                    disabled={refreshing}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-[rgba(0,0,0,0.08)] bg-white px-3.5 py-2 text-sm font-medium text-[#71717a] transition-colors hover:text-[#0f0f17] disabled:opacity-50"
                  >
                    <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} /> Rebuild
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setEditing((e) => !e)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-[rgba(0,0,0,0.08)] bg-white px-3.5 py-2 text-sm font-medium text-[#71717a] transition-colors hover:text-[#0f0f17]"
                >
                  <Pencil className="size-4" /> {editing ? "Close editor" : "Edit details"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Inline editor (skills / education / links) ── */}
      {editing && (
        <form onSubmit={saveDetails} className="space-y-4 rounded-2xl border border-[#5b5bd6]/30 bg-white p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-[#0f0f17]">Edit profile details</h3>
            <button type="button" onClick={() => setEditing(false)} aria-label="Close" className="text-[#71717a] hover:text-[#0f0f17]">
              <X className="size-4" />
            </button>
          </div>

          {/* Target role */}
          <div>
            <label className="mb-1 block text-xs font-medium text-[#71717a]">Target role</label>
            <input
              value={form.target_role}
              onChange={(e) => setField("target_role", e.target.value)}
              className={INPUT}
              placeholder="e.g. Senior Backend Engineer"
            />
          </div>

          {/* Skills */}
          <div>
            <label className="mb-1 block text-xs font-medium text-[#71717a]">Skills</label>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {form.key_skills.map((s, i) => (
                <span key={`${s}-${i}`} className="inline-flex items-center gap-1 rounded-full border border-[rgba(91,91,214,0.2)] bg-[#ededf8] py-1 pl-2.5 pr-1 text-xs font-medium text-[#3d3d80]">
                  {s}
                  <button
                    type="button"
                    onClick={() => setField("key_skills", form.key_skills.filter((_, j) => j !== i))}
                    aria-label={`Remove ${s}`}
                    className="grid size-4 place-items-center rounded-full text-[#5b5bd6] hover:bg-[rgba(91,91,214,0.15)]"
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            </div>
            <input
              value={skillDraft}
              onChange={(e) => setSkillDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addSkill(skillDraft);
                }
              }}
              onBlur={() => addSkill(skillDraft)}
              className={INPUT}
              placeholder="Add a skill and press Enter"
            />
          </div>

          {/* Education */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-medium text-[#71717a]">Education</label>
              <button
                type="button"
                onClick={() => setField("education", [...form.education, emptyEducation()])}
                className="text-xs font-medium text-[#5b5bd6] hover:text-[#4f4fc9]"
              >
                + Add
              </button>
            </div>
            <div className="space-y-2">
              {form.education.map((ed, i) => (
                <div key={i} className="grid gap-2 rounded-xl border border-[rgba(0,0,0,0.06)] bg-[#faf9f7] p-3 sm:grid-cols-2">
                  <input value={ed.institution} onChange={(e) => setField("education", form.education.map((x, j) => (j === i ? { ...x, institution: e.target.value } : x)))} className={INPUT} placeholder="Institution" />
                  <input value={ed.dates} onChange={(e) => setField("education", form.education.map((x, j) => (j === i ? { ...x, dates: e.target.value } : x)))} className={INPUT} placeholder="Dates" />
                  <input value={ed.degree} onChange={(e) => setField("education", form.education.map((x, j) => (j === i ? { ...x, degree: e.target.value } : x)))} className={INPUT} placeholder="Degree" />
                  <input value={ed.field_of_study} onChange={(e) => setField("education", form.education.map((x, j) => (j === i ? { ...x, field_of_study: e.target.value } : x)))} className={INPUT} placeholder="Field of study" />
                  <button type="button" onClick={() => setField("education", form.education.filter((_, j) => j !== i))} className="justify-self-start text-xs text-[#71717a] hover:text-rose-600 sm:col-span-2">
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Links */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-medium text-[#71717a]">Links</label>
              <button type="button" onClick={() => setField("links", [...form.links, emptyLink()])} className="text-xs font-medium text-[#5b5bd6] hover:text-[#4f4fc9]">
                + Add
              </button>
            </div>
            <div className="space-y-2">
              {form.links.map((lnk, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]">
                  <input value={lnk.label} onChange={(e) => setField("links", form.links.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} className={INPUT} placeholder="Label" />
                  <input value={lnk.url} onChange={(e) => setField("links", form.links.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} className={INPUT} placeholder="https://…" />
                  <button type="button" onClick={() => setField("links", form.links.filter((_, j) => j !== i))} className="rounded-xl border border-[rgba(0,0,0,0.08)] px-3 text-sm text-[#71717a] hover:text-[#0f0f17]">
                    <Link2 className="size-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button type="submit" disabled={saving} className="rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28] disabled:opacity-50">
              {saving ? "Saving…" : "Save profile"}
            </button>
            <button type="button" onClick={() => setEditing(false)} className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-white px-4 py-2.5 text-sm font-medium text-[#71717a] hover:text-[#0f0f17]">
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
