from __future__ import annotations

import asyncio
import io
import re
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from backend.schemas import (
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeIdentity,
    ResumeProjectItem,
    ResumeTailorerOutput,
)

_PDFLATEX = "pdflatex"
_TIMEOUT_S = 60
_LOG_TAIL_CHARS = 2000
_LATEX_FORMAT = Path("assets/latex-format.tex")


class ResumeTemplateError(RuntimeError):
    """The LaTeX resume template could not be rendered or compiled."""


def load_latex_format() -> str:
    """Read the fixed resume layout used for generated PDFs."""
    return _LATEX_FORMAT.read_text()


def escape_latex(value: str | None) -> str:
    """Escape model/user text so it can be inserted into LaTeX safely."""
    if not value:
        return ""
    text = (
        value.replace("\u2014", "---")
        .replace("\u2013", "--")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2022", "-")
        .replace("\u2026", "...")
        .replace("\u2192", "->")
        .replace("\u2190", "<-")
        .replace("\u2265", ">=")
        .replace("\u2264", "<=")
        .replace("\u00d7", "x")
        .replace("\u2713", "yes")
        .replace("\u20b9", "INR ")
        .replace("\u00a0", " ")
    )
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "<": r"\textless{}",
        ">": r"\textgreater{}",
        "£": r"\pounds{}",
        "€": r"\texteuro{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _limit_words(value: str, max_words: int | None) -> str:
    """Trim text toward a word budget WITHOUT ever cutting a sentence in half.

    Over budget, drop whole trailing sentences. If even the first sentence exceeds
    the budget, keep it whole rather than amputate it mid-clause and bolt on a fake
    period (the "giving the team better." defect). One-page fit is handled by the
    bullet/entry caps and the compact + overflow fallbacks in render_resume_pdf, not
    by mutilating prose. ``max_words=None`` disables the budget entirely — used by
    the faithful (WYSIWYG) download path, which never truncates curated content.
    """
    cleaned = _clean(value)
    if max_words is None:
        return cleaned
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    kept: list[str] = []
    count = 0
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if kept and count + sentence_words > max_words:
            break
        kept.append(sentence)
        count += sentence_words
    return " ".join(kept) if kept else cleaned


def _bullet_list(
    items: list[str], *, limit: int, max_words: int = 24, faithful: bool = False
) -> str:
    cleaned = [_clean(item) for item in items if _clean(item)]
    bullets = cleaned if faithful else cleaned[:limit]
    if not bullets:
        return ""
    word_cap = None if faithful else max_words
    body = "\n".join(f"  \\item {escape_latex(_limit_words(item, word_cap))}" for item in bullets)
    return "\\begin{itemize}\n" + body + "\n\\end{itemize}"


def _render_experience_item(
    item: ResumeExperienceItem, *, compact: bool = False, faithful: bool = False
) -> str:
    company = escape_latex(_clean(item.company))
    role = escape_latex(_clean(item.role))
    dates = escape_latex(_clean(item.dates))
    bullets = _bullet_list(
        item.bullets,
        limit=2 if compact else 3,
        max_words=18 if compact else 24,
        faithful=faithful,
    )
    if not any([company, role, dates, bullets]):
        return ""
    heading = f"\\resumeheading{{{company}}}{{}}{{{role}}}{{{dates}}}"
    return "\n".join(part for part in [heading, bullets] if part)


def _render_experience(
    items: list[ResumeExperienceItem], *, compact: bool = False, faithful: bool = False
) -> str:
    selected = items if faithful else items[: 2 if compact else 3]
    rendered = [
        _render_experience_item(item, compact=compact, faithful=faithful) for item in selected
    ]
    return "\n\n".join(item for item in rendered if item)


def _render_project_item(
    item: ResumeProjectItem, *, compact: bool = False, faithful: bool = False
) -> str:
    name = escape_latex(_clean(item.name))
    description = escape_latex(
        _limit_words(item.description or "", None if faithful else (6 if compact else 10))
    )
    bullets = _bullet_list(
        item.bullets,
        limit=1 if compact else 2,
        max_words=16 if compact else 22,
        faithful=faithful,
    )
    if not any([name, description, bullets]):
        return ""
    heading = f"\\projectheading{{{name}}}{{{description}}}{{}}"
    return "\n".join(part for part in [heading, bullets] if part)


def _render_projects(
    items: list[ResumeProjectItem], *, compact: bool = False, faithful: bool = False
) -> str:
    selected = items if faithful else items[: 2 if compact else 3]
    rendered = [_render_project_item(item, compact=compact, faithful=faithful) for item in selected]
    return "\n\n".join(item for item in rendered if item)


def _render_skills(skills: list[str], *, compact: bool = False, faithful: bool = False) -> str:
    cleaned = [escape_latex(_clean(skill)) for skill in skills if _clean(skill)]
    selected = cleaned if faithful else cleaned[: 16 if compact else 24]
    if not selected:
        return (
            r"  \textbf{Relevant Skills} & "
            r"Tailored skills available in the application package \\[0.4pt]"
        )
    return r"  \textbf{Relevant Skills} & " + ", ".join(selected) + r" \\[0.4pt]"


def _render_education_item(item: ResumeEducationItem) -> str:
    institution = escape_latex(_clean(item.institution))
    degree = escape_latex(_clean(item.degree))
    dates = escape_latex(_clean(item.dates))
    if not any([institution, degree, dates]):
        return ""
    return f"\\resumeheading{{{institution}}}{{}}{{{degree}}}{{{dates}}}"


def _render_education(items: list[ResumeEducationItem], *, faithful: bool = False) -> str:
    selected = items if faithful else items[:2]
    rendered = [_render_education_item(item) for item in selected]
    return "\n\n".join(item for item in rendered if item)


def _render_header(identity: ResumeIdentity, *, headline: str = "") -> str:
    """Build the centered name + contact + links block from the user's own identity.

    Each piece is optional and omitted cleanly (no dangling separators) so a sparse
    profile still produces a valid header — and never another user's details. The
    optional ``headline`` renders as a tagline under the name so a title edited in
    the resume editor reaches the PDF; it is suppressed when it merely repeats the
    name (a common default) to avoid printing the name twice.
    """
    sep = r" $\cdot$ "
    name = escape_latex(_clean(identity.name))
    tagline = _clean(headline)
    if tagline and tagline.casefold() == _clean(identity.name).casefold():
        tagline = ""

    contact: list[str] = []
    if identity.location.strip():
        contact.append(escape_latex(_clean(identity.location)))
    if identity.email.strip():
        email = escape_latex(_clean(identity.email))
        contact.append(rf"\href{{mailto:{email}}}{{{email}}}")
    if identity.phone.strip():
        contact.append(escape_latex(_clean(identity.phone)))

    links: list[str] = []
    for link in identity.links:
        url = _clean(link.url)
        if not url:
            continue
        label = escape_latex(_clean(link.label) or url)
        links.append(rf"\href{{{escape_latex(url)}}}{{{label}}}")

    lines: list[str] = []
    if name:
        lines.append(rf"    {{\LARGE \textbf{{{name}}}}} \\[3pt]")
    if tagline:
        lines.append(rf"    {{\normalsize \textit{{{escape_latex(tagline)}}}}} \\[2pt]")
    if contact:
        lines.append(rf"    \small {sep.join(contact)} \\[2pt]")
    if links:
        lines.append("    " + sep.join(links))
    if not lines:
        return ""
    return "\\begin{center}\n" + "\n".join(lines) + "\n\\end{center}"


def render_resume_latex(
    output: ResumeTailorerOutput,
    template: str | None = None,
    *,
    identity: ResumeIdentity | None = None,
    compact: bool = False,
    faithful: bool = False,
) -> str:
    """Render structured resume output into the fixed LaTeX format.

    The model controls content only. This renderer owns the LaTeX structure,
    escaping, the per-user header, and one-page-oriented content caps. ``faithful``
    renders the curated content in full (no summary/bullet/entry caps) for the
    WYSIWYG download path, matching the DOCX and on-screen preview; it takes
    precedence over ``compact``.
    """
    source = template if template is not None else load_latex_format()
    summary_cap = None if faithful else (36 if compact else 52)
    summary = escape_latex(_limit_words(output.summary or output.headline, summary_cap))
    replacements = {
        "%%JOBFIT_HEADER%%": _render_header(identity or ResumeIdentity(), headline=output.headline),
        "%%JOBFIT_SUMMARY%%": summary or "Tailored summary available in the application package.",
        "%%JOBFIT_EXPERIENCE%%": _render_experience(
            output.experience, compact=compact, faithful=faithful
        ),
        "%%JOBFIT_PROJECTS%%": _render_projects(
            output.projects, compact=compact, faithful=faithful
        ),
        "%%JOBFIT_SKILLS%%": _render_skills(output.skills, compact=compact, faithful=faithful),
        "%%JOBFIT_EDUCATION%%": _render_education(output.education, faithful=faithful),
    }
    rendered = source
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    missing = sorted(set(re.findall(r"%%JOBFIT_[A-Z_]+%%", rendered)))
    if missing:
        raise ResumeTemplateError(f"Unfilled resume template markers: {', '.join(missing)}")
    return rendered


def _run_pdflatex(tex_path: str, out_dir: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _PDFLATEX,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            out_dir,
            tex_path,
        ],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
    )


def _page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


async def compile_latex_to_pdf(tex: str, *, require_one_page: bool = True) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / "resume.tex"
        tex_path.write_text(tex)
        try:
            proc = await asyncio.to_thread(_run_pdflatex, str(tex_path), tmp)
        except FileNotFoundError as exc:
            raise ResumeTemplateError("pdflatex is not installed or is not on PATH") from exc
        pdf_path = Path(tmp) / "resume.pdf"
        if proc.returncode != 0 or not pdf_path.exists():
            log_path = Path(tmp) / "resume.log"
            log = log_path.read_text() if log_path.exists() else (proc.stdout or proc.stderr or "")
            raise ResumeTemplateError(f"pdflatex failed. Log tail:\n{log[-_LOG_TAIL_CHARS:]}")
        pdf = pdf_path.read_bytes()

    if require_one_page and _page_count(pdf) > 1:
        raise ResumeTemplateError("Generated resume exceeded one page")
    return pdf


async def render_resume_pdf(
    output: ResumeTailorerOutput,
    identity: ResumeIdentity | None = None,
    *,
    faithful: bool = False,
) -> bytes:
    """Compile the resume to PDF.

    ``faithful`` renders the curated content in full over as many pages as it
    needs — the WYSIWYG download the user sees in the editor/preview. The default
    (auto-generated) path keeps the one-page discipline, falling back to a compact
    render and finally an uncapped multi-page render only if it overflows.
    """
    if faithful:
        return await compile_latex_to_pdf(
            render_resume_latex(output, identity=identity, faithful=True),
            require_one_page=False,
        )
    try:
        return await compile_latex_to_pdf(
            render_resume_latex(output, identity=identity), require_one_page=True
        )
    except ResumeTemplateError as exc:
        if "exceeded one page" not in str(exc):
            raise

    compact_tex = render_resume_latex(output, identity=identity, compact=True)
    try:
        return await compile_latex_to_pdf(compact_tex, require_one_page=True)
    except ResumeTemplateError as exc:
        if "exceeded one page" not in str(exc):
            raise
        return await compile_latex_to_pdf(compact_tex, require_one_page=False)
