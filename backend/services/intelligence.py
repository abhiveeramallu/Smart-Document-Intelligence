from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

try:
    from config import MAX_CONTEXT_CHARS
    from services.ollama_client import OllamaClient
except ModuleNotFoundError:
    from backend.config import MAX_CONTEXT_CHARS
    from backend.services.ollama_client import OllamaClient


ENTITY_KEYS = [
    "names",
    "dates",
    "amounts",
    "addresses",
    "organizations",
    "emails",
    "phones",
]


@dataclass
class EntityMatch:
    entity_type: str
    value: str
    confidence: float
    snippet: str
    start_index: int | None
    end_index: int | None


def _find_span(text: str, needle: str) -> tuple[int | None, int | None]:
    if not needle:
        return None, None
    index = text.lower().find(needle.lower())
    if index < 0:
        return None, None
    return index, index + len(needle)


def _snippet(text: str, start: int | None, end: int | None, radius: int = 80) -> str:
    if start is None or end is None:
        return ""
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip()


def fallback_entities(text: str) -> list[EntityMatch]:
    if not text.strip():
        return []

    patterns: dict[str, str] = {
        "emails": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "phones": r"(?:\+?\d{1,2}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}",
        "amounts": r"(?:USD\s*)?\$\s?\d[\d,]*(?:\.\d{2})?",
        "dates": r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})",
        "addresses": r"\b\d{1,6}\s+[A-Za-z0-9\s]{2,40}\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b[^\n,]*",
        "organizations": r"\b[A-Z][A-Za-z0-9&.,\-\s]{2,40}\s(?:Inc|LLC|Ltd|Corp|Corporation|University|Bank|Agency)\b",
        "names": r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b",
    }

    found: list[EntityMatch] = []
    for entity_type, pattern in patterns.items():
        seen: set[str] = set()
        for match in re.finditer(pattern, text):
            value = match.group().strip()
            if len(value) < 3:
                continue
            normalized = value.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            found.append(
                EntityMatch(
                    entity_type=entity_type,
                    value=value,
                    confidence=0.58,
                    snippet=_snippet(text, match.start(), match.end()),
                    start_index=match.start(),
                    end_index=match.end(),
                )
            )
    return found


def normalize_entities(payload: dict[str, Any], text: str) -> list[EntityMatch]:
    entities_obj = payload.get("entities")
    if not isinstance(entities_obj, dict):
        return fallback_entities(text)

    output: list[EntityMatch] = []
    seen: set[tuple[str, str]] = set()

    for entity_type in ENTITY_KEYS:
        items = entities_obj.get(entity_type, [])
        if not isinstance(items, list):
            continue

        for item in items:
            value = ""
            confidence = 0.8
            snippet = ""
            if isinstance(item, dict):
                value = str(item.get("value") or item.get("text") or "").strip()
                confidence = float(item.get("confidence", 0.8) or 0.8)
                snippet = str(item.get("snippet") or "").strip()
            else:
                value = str(item).strip()

            if not value:
                continue
            signature = (entity_type, value.lower())
            if signature in seen:
                continue
            seen.add(signature)

            start, end = _find_span(text, value)
            if not snippet:
                snippet = _snippet(text, start, end)

            output.append(
                EntityMatch(
                    entity_type=entity_type,
                    value=value,
                    confidence=max(0.0, min(1.0, confidence)),
                    snippet=snippet,
                    start_index=start,
                    end_index=end,
                )
            )

    if output:
        return output
    return fallback_entities(text)


def _brief_summary(text: str) -> str:
    if not text.strip():
        return "No readable text was extracted."
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return " ".join(sentences[:2])[:360]


def _detailed_summary(text: str) -> str:
    if not text.strip():
        return "No readable text was extracted from this document."
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    top = lines[:8]
    return " ".join(top)[:900]


def analyze_document(
    *,
    text: str,
    filename: str,
    ollama: OllamaClient,
    image_bytes: list[bytes] | None = None,
) -> dict[str, Any]:
    clipped_text = text[:MAX_CONTEXT_CHARS]
    system_prompt = (
        "You are a local document intelligence engine. "
        "Return strict JSON with this schema: "
        "{\"summary_brief\":string,\"summary_detailed\":string,\"bullet_points\":string[],"
        "\"entities\":{\"names\":[],\"dates\":[],\"amounts\":[],\"addresses\":[],"
        "\"organizations\":[],\"emails\":[],\"phones\":[]},"
        "\"highlights\":[{\"label\":string,\"value\":string,\"snippet\":string}]}"
    )
    user_prompt = (
        f"Document filename: {filename}\n"
        "Identify key information and provide concise summaries. "
        "If the content is unclear, leave uncertain values out instead of hallucinating.\n"
        f"Document content:\n{clipped_text if clipped_text else '[no extracted text]'}"
    )

    model_output: dict[str, Any] = {}
    try:
        model_output = ollama.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=image_bytes,
        )
    except Exception:
        model_output = {}

    summary_brief = str(model_output.get("summary_brief") or _brief_summary(text)).strip()
    summary_detailed = str(model_output.get("summary_detailed") or _detailed_summary(text)).strip()

    bullets_raw = model_output.get("bullet_points", [])
    bullet_points = [str(item).strip() for item in bullets_raw if str(item).strip()] if isinstance(bullets_raw, list) else []
    if not bullet_points:
        bullet_points = [point for point in re.split(r"[\n•-]+", _brief_summary(text)) if point.strip()][:5]

    highlights_raw = model_output.get("highlights", [])
    highlights: list[dict[str, str]] = []
    if isinstance(highlights_raw, list):
        for item in highlights_raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "Key detail").strip()
            value = str(item.get("value") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if value:
                highlights.append({"label": label, "value": value, "snippet": snippet})

    entities = normalize_entities(model_output, text)
    if not highlights and entities:
        highlights = [
            {"label": entity.entity_type, "value": entity.value, "snippet": entity.snippet}
            for entity in entities[:10]
        ]

    return {
        "summary_brief": summary_brief,
        "summary_detailed": summary_detailed,
        "bullet_points": bullet_points,
        "entities": [entity.__dict__ for entity in entities],
        "highlights": highlights,
        "model_output": model_output,
    }


def summarize_document(*, text: str, level: str, ollama: OllamaClient) -> dict[str, Any]:
    clipped_text = text[:MAX_CONTEXT_CHARS]
    instructions = {
        "brief": "Produce a concise 2-3 sentence summary.",
        "detailed": "Produce a detailed summary in 3-6 paragraphs.",
        "bullets": "Produce a concise bullet-point summary.",
    }
    system_prompt = (
        "Return strict JSON with schema {\"level\":string,\"content\":string,\"bullets\":string[]}"
    )
    user_prompt = (
        f"Requested level: {level}\n"
        f"Instruction: {instructions.get(level, instructions['brief'])}\n"
        f"Document content:\n{clipped_text if clipped_text else '[no extracted text]'}"
    )
    try:
        response = ollama.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        response = {}

    if level == "bullets":
        raw_bullets = response.get("bullets", [])
        bullets = [str(item).strip() for item in raw_bullets if str(item).strip()] if isinstance(raw_bullets, list) else []
        if not bullets:
            bullets = [line.strip() for line in re.split(r"[\n•-]+", _detailed_summary(text)) if line.strip()][:8]
        return {"level": level, "content": "\n".join(f"- {item}" for item in bullets), "bullets": bullets}

    content = str(response.get("content") or "").strip()
    if not content:
        content = _brief_summary(text) if level == "brief" else _detailed_summary(text)
    return {"level": level, "content": content, "bullets": []}


def compare_documents(
    *,
    left_name: str,
    left_text: str,
    right_name: str,
    right_text: str,
    ollama: OllamaClient,
) -> dict[str, Any]:
    left_lines = [line for line in left_text.splitlines() if line.strip()]
    right_lines = [line for line in right_text.splitlines() if line.strip()]

    similarity = difflib.SequenceMatcher(None, left_text[:MAX_CONTEXT_CHARS], right_text[:MAX_CONTEXT_CHARS]).ratio()
    diff_lines = list(
        difflib.unified_diff(
            left_lines[:180],
            right_lines[:180],
            fromfile=left_name,
            tofile=right_name,
            lineterm="",
            n=2,
        )
    )

    system_prompt = (
        "Compare two document versions and return strict JSON schema: "
        "{\"summary\":string,\"changes\":[{\"type\":string,\"description\":string,\"impact\":string}]}"
    )
    user_prompt = (
        f"Left document ({left_name}):\n{left_text[:MAX_CONTEXT_CHARS]}\n\n"
        f"Right document ({right_name}):\n{right_text[:MAX_CONTEXT_CHARS]}"
    )

    response: dict[str, Any] = {}
    try:
        response = ollama.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        response = {}

    changes = response.get("changes", []) if isinstance(response.get("changes"), list) else []
    normalized_changes: list[dict[str, str]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        normalized_changes.append(
            {
                "type": str(change.get("type") or "change").strip(),
                "description": str(change.get("description") or "").strip(),
                "impact": str(change.get("impact") or "").strip(),
            }
        )

    if not normalized_changes:
        for line in diff_lines[:12]:
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            change_type = "removed" if line.startswith("-") else "added" if line.startswith("+") else "context"
            normalized_changes.append(
                {
                    "type": change_type,
                    "description": line[1:].strip(),
                    "impact": "Review",
                }
            )

    summary = str(response.get("summary") or "").strip()
    if not summary:
        summary = (
            f"Similarity score is {similarity:.2f}. "
            f"Detected {len(normalized_changes)} notable line-level differences."
        )

    return {
        "summary": summary,
        "similarity": round(similarity, 4),
        "changes": normalized_changes[:30],
        "diff_preview": diff_lines[:220],
    }
