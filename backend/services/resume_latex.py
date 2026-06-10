from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from backend.agents.base import SONNET, BaseAgent

logger = logging.getLogger(__name__)

# NOTE: real runs require a TeX distribution — `pdflatex` must be on PATH
# (e.g. texlive). Tests mock subprocess.run, so CI does not need texlive.
_PDFLATEX = "pdflatex"
_TIMEOUT_S = 60
_LOG_TAIL_CHARS = 2000
_RESUME_TEX = Path("assets/resume.tex")

_SYSTEM = (
    "You are editing a LaTeX resume to target a specific job. Edit ONLY the "
    "summary text, the skills list, and the experience bullet points so they "
    "emphasise relevance to the job. PRESERVE everything else exactly as-is: "
    "the preamble, \\documentclass, packages, custom macros, layout, and overall "
    "document structure. "
    "LENGTH: the resume MUST remain ONE page. The tailored version must be no "
    "longer than the original — do NOT add bullets, sections, or sentences, and do "
    "NOT lengthen the summary. To emphasise relevance, rewrite or shorten existing "
    "text in place; if space is tight, cut or condense the least-relevant bullets "
    "so it fits on one page. "
    "Return ONLY the complete modified .tex source — no commentary and no markdown "
    "code fences."
)


class ResumeCompileError(RuntimeError):
    """pdflatex failed to produce a PDF even after one self-correction retry."""


class _ResumeLatexAgent(BaseAgent):
    # LaTeX editing must keep structure valid → use the stronger model.
    model = SONNET

    async def run(self, system: str, user: str) -> str:
        return await self._call(system, user)


def _strip_fences(text: str) -> str:
    """Drop a leading ```/```latex fence and trailing ``` if the model added them."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if "```" in t:
            t = t[: t.rfind("```")]
    return t.strip()


async def _tailor_latex(
    job_description: str, latex_source: str, correction_log: str | None = None
) -> str:
    """Ask the LLM for a job-tailored .tex. Patched out in tests."""
    system = _SYSTEM
    if correction_log:
        system += (
            "\n\nYour previous .tex FAILED to compile with pdflatex. Fix the LaTeX "
            "error (keep the same tailoring intent). pdflatex log tail:\n" + correction_log
        )
    user = f"## Job description\n{job_description}\n\n## Current resume.tex\n{latex_source}"
    raw = await _ResumeLatexAgent().run(system, user)
    return _strip_fences(raw)


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


async def _compile(tex: str) -> tuple[bytes | None, str]:
    """Compile a .tex string → (pdf bytes | None, log tail). The PDF is read
    inside the TemporaryDirectory, before it is cleaned up."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "resume.tex").write_text(tex)
        proc = await asyncio.to_thread(_run_pdflatex, str(Path(tmp) / "resume.tex"), tmp)
        pdf_path = Path(tmp) / "resume.pdf"
        if proc.returncode == 0 and pdf_path.exists():
            return pdf_path.read_bytes(), ""
        log_path = Path(tmp) / "resume.log"
        log = log_path.read_text() if log_path.exists() else (proc.stdout or "")
        return None, log[-_LOG_TAIL_CHARS:]


async def tailor_resume_pdf(job_description: str, latex_source: str) -> bytes:
    """Tailor a LaTeX resume to a job and compile it to PDF bytes.

    The LLM edits only summary/skills/experience; pdflatex compiles. On compile
    failure, retry ONCE with a self-correction prompt carrying the pdflatex log
    tail. Raises ResumeCompileError if the second attempt also fails.
    """
    tex = await _tailor_latex(job_description, latex_source)
    pdf, log = await _compile(tex)
    if pdf is not None:
        return pdf

    tex = await _tailor_latex(job_description, latex_source, correction_log=log)
    pdf, log = await _compile(tex)
    if pdf is not None:
        return pdf

    raise ResumeCompileError(f"pdflatex failed after self-correction retry. Log tail:\n{log}")


def load_resume_latex() -> str:
    """Read the base resume .tex template from assets/resume.tex."""
    return _RESUME_TEX.read_text()
