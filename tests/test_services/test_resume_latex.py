# tests/test_services/test_resume_latex.py
#
# pdflatex is mocked here so CI does not need a TeX distribution installed.
# Real runs require texlive (pdflatex on PATH).
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

VALID_TEX = r"\documentclass{article}\begin{document}Hello\end{document}"


def _success_run(cmd, **kwargs):
    """Fake pdflatex that 'compiles' — writes a dummy PDF into -output-directory."""
    out = cmd[cmd.index("-output-directory") + 1]
    Path(out, "resume.pdf").write_bytes(b"%PDF-1.4 compiled")
    return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")


async def test_command_shape_and_returns_pdf_bytes():
    with (
        patch(
            "backend.services.resume_latex._tailor_latex",
            new_callable=AsyncMock,
            return_value=VALID_TEX,
        ),
        patch("backend.services.resume_latex.subprocess.run", side_effect=_success_run) as mrun,
    ):
        from backend.services.resume_latex import tailor_resume_pdf

        pdf = await tailor_resume_pdf("Backend Engineer role", VALID_TEX)

    assert pdf == b"%PDF-1.4 compiled"
    assert mrun.call_count == 1
    cmd = mrun.call_args.args[0]
    assert cmd[0] == "pdflatex"
    assert "-interaction=nonstopmode" in cmd
    assert "-halt-on-error" in cmd
    assert "-output-directory" in cmd
    assert cmd[-1].endswith("resume.tex")


async def test_retry_once_then_success_feeds_log_to_correction():
    state = {"n": 0}

    def run(cmd, **kwargs):
        state["n"] += 1
        out = cmd[cmd.index("-output-directory") + 1]
        if state["n"] == 1:
            Path(out, "resume.log").write_text("! Undefined control sequence.\nl.5 \\bad")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        Path(out, "resume.pdf").write_bytes(b"%PDF ok-2")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    tailor = AsyncMock(return_value=VALID_TEX)
    with (
        patch("backend.services.resume_latex._tailor_latex", tailor),
        patch("backend.services.resume_latex.subprocess.run", side_effect=run) as mrun,
    ):
        from backend.services.resume_latex import tailor_resume_pdf

        pdf = await tailor_resume_pdf("Backend Engineer role", VALID_TEX)

    assert pdf == b"%PDF ok-2"
    assert mrun.call_count == 2
    assert tailor.await_count == 2
    # the retry must be a self-correction prompt carrying the pdflatex log tail
    second = tailor.await_args_list[1]
    assert second.kwargs.get("correction_log")
    assert "Undefined control sequence" in second.kwargs["correction_log"]


async def test_raises_after_two_failures():
    def run(cmd, **kwargs):
        out = cmd[cmd.index("-output-directory") + 1]
        Path(out, "resume.log").write_text("! Emergency stop.")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    from backend.services.resume_latex import ResumeCompileError

    with (
        patch(
            "backend.services.resume_latex._tailor_latex",
            new_callable=AsyncMock,
            return_value=VALID_TEX,
        ),
        patch("backend.services.resume_latex.subprocess.run", side_effect=run) as mrun,
    ):
        from backend.services.resume_latex import tailor_resume_pdf

        with pytest.raises(ResumeCompileError):
            await tailor_resume_pdf("Backend Engineer role", VALID_TEX)

    assert mrun.call_count == 2
