from __future__ import annotations

import asyncio
import io
from pathlib import Path

from pypdf import PdfReader


def _extract_sync(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_sync, pdf_bytes)


async def extract_text_from_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return await extract_text_from_pdf_bytes(p.read_bytes())
