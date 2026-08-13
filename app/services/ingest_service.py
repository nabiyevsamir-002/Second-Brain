"""Ingest iş axını (Phase 3) — link/forward və PDF/DOCX → qeyd.

- ingest_url: veb səhifəni gətir → mətn çıxar → Claude xülasələ → embedding → saxla.
- ingest_document: PDF/DOCX → mətn çıxar → hissələ (chunk) → batch embedding → saxla.
Bu servislər "splittable"-dır: gələcəkdə agent tool-larına (fetch_url,
ingest_document) çevrilə bilər.
"""

from __future__ import annotations

import io
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_conf import get_logger
from app.models import Note, NoteSource
from app.repositories.notes import create_note
from app.services.notes_service import _parse_json

log = get_logger("ingest")

SUMMARIZE_SYSTEM = (
    "Sənə bir veb səhifə və ya sənəd mətni verilir. Azərbaycanca YALNIZ bu JSON-u qaytar:\n"
    '{"summary": "1-2 cümləlik xülasə", "category": "bir sözlük kateqoriya", '
    '"tags": ["3-5", "açar", "söz"]}'
)

MAX_SUMMARY_INPUT = 8000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


async def _summarize(llm: Any, content: str) -> dict[str, Any]:
    resp = await llm.complete(
        system=SUMMARIZE_SYSTEM,
        messages=[{"role": "user", "content": content[:MAX_SUMMARY_INPUT]}],
        model=settings.claude_model_fast,
        max_tokens=1024,
    )
    return _parse_json(llm.text_of(resp))


# --- URL / forward ---------------------------------------------------------

async def fetch_url_text(url: str) -> tuple[str, str]:
    """Veb səhifəni gətir, başlıq və təmiz mətni qaytar."""
    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; SecondBrainBot/1.0)"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        title = (soup.title.string if soup.title and soup.title.string else "").strip()
        text = soup.get_text("\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return title, text


async def ingest_url(
    session: AsyncSession, llm: Any, embedder: Any, user_id: int, url: str
) -> Note:
    title, text = await fetch_url_text(url)
    domain = urlparse(url).netloc

    meta: dict[str, Any] = {}
    if llm is not None and text:
        meta = await _summarize(llm, f"URL: {url}\nBaşlıq: {title}\n\n{text}")

    summary = (meta.get("summary") or "").strip() or None
    category = (meta.get("category") or "").strip() or "link"
    tags = [str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()][:5]
    if domain and domain not in tags:
        tags.append(domain)

    embedding = None
    if embedder is not None:
        embed_src = "\n".join(x for x in (summary, title, text[:1500]) if x)
        embedding = await embedder.embed_one(embed_src)

    raw = "\n".join(x for x in (title, url, "", text[:4000]) if x is not None)
    note = await create_note(
        session,
        user_id,
        raw,
        NoteSource.forward,
        cleaned_text=None,
        summary=summary,
        category=category,
        tags=tags,
        embedding=embedding,
    )
    log.info("url_ingested", note_id=note.id, url=url, chars=len(text))
    return note


# --- PDF / DOCX ------------------------------------------------------------

def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    chunks: list[str] = []
    step = max(1, size - overlap)
    for i in range(0, len(text), step):
        piece = text[i : i + size].strip()
        if piece:
            chunks.append(piece)
    return chunks


async def ingest_document(
    session: AsyncSession,
    llm: Any,
    embedder: Any,
    user_id: int,
    filename: str,
    data: bytes,
) -> tuple[list[Note], str | None]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        text = _extract_pdf(data)
        source = NoteSource.pdf
    elif ext == "docx":
        text = _extract_docx(data)
        source = NoteSource.docx
    else:
        raise ValueError("yalnız PDF və DOCX")

    text = text.strip()
    if not text:
        raise ValueError("sənəddən mətn çıxarıla bilmədi")

    meta: dict[str, Any] = {}
    if llm is not None:
        meta = await _summarize(llm, text)
    summary = (meta.get("summary") or "").strip() or None
    category = (meta.get("category") or "").strip() or "sənəd"
    tags = [str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()][:4]
    tags.append(filename[:40])

    chunks = chunk_text(text)
    embeddings: list[Any] = [None] * len(chunks)
    if embedder is not None and chunks:
        embeddings = await embedder.embed(chunks)  # tək API çağırışı (batch)

    notes: list[Note] = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        note = await create_note(
            session,
            user_id,
            chunk,
            source,
            cleaned_text=None,
            summary=summary if idx == 0 else None,
            category=category,
            tags=tags,
            embedding=emb,
        )
        notes.append(note)

    log.info("document_ingested", filename=filename, chunks=len(notes), source=source.value)
    return notes, summary
