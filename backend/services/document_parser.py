from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from docx import Document as DocxDocument

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency at runtime
    pytesseract = None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append((page.extract_text() or "").strip())
    return "\n\n".join(part for part in pages if part).strip()


def extract_text_from_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    parts = [
        paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()
    ]
    return "\n".join(parts).strip()


def extract_text_from_txt(path: Path) -> str:
    content = path.read_bytes()
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore").strip()


def extract_text_from_image(path: Path) -> str:
    if pytesseract is None:
        return ""
    image = Image.open(path)
    return pytesseract.image_to_string(image).strip()


def parse_document(path: Path, file_type: str) -> str:
    if file_type == "pdf":
        return extract_text_from_pdf(path)
    if file_type == "docx":
        return extract_text_from_docx(path)
    if file_type == "txt":
        return extract_text_from_txt(path)
    if file_type in {"png", "jpg", "jpeg"}:
        return extract_text_from_image(path)
    return ""


def build_preview(text: str, max_chars: int = 360) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def chunk_text(text: str, chunk_chars: int = 1200, overlap: int = 180) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    cursor = 0
    text_len = len(cleaned)
    while cursor < text_len:
        end = min(cursor + chunk_chars, text_len)
        candidate = cleaned[cursor:end]

        if end < text_len:
            last_break = candidate.rfind("\n\n")
            if last_break > chunk_chars // 2:
                end = cursor + last_break
                candidate = cleaned[cursor:end]

        chunk = candidate.strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break
        cursor = max(end - overlap, 0)

    return chunks
