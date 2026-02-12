from __future__ import annotations

import csv
import io
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

try:
    from config import (
        DB_PATH,
        MAX_UPLOAD_BYTES,
        OLLAMA_BASE_URL,
        OLLAMA_MODEL,
        OLLAMA_VISION_MODEL,
        SUPPORTED_EXTENSIONS,
        UPLOAD_DIR,
    )
    from database import Database
    from services.document_parser import (
        build_preview,
        chunk_text,
        parse_document,
        sha256_bytes,
    )
    from services.intelligence import (
        analyze_document,
        compare_documents,
        summarize_document,
    )
    from services.ollama_client import OllamaClient, OllamaConfig
except ModuleNotFoundError:
    from backend.config import (
        DB_PATH,
        MAX_UPLOAD_BYTES,
        OLLAMA_BASE_URL,
        OLLAMA_MODEL,
        OLLAMA_VISION_MODEL,
        SUPPORTED_EXTENSIONS,
        UPLOAD_DIR,
    )
    from backend.database import Database
    from backend.services.document_parser import (
        build_preview,
        chunk_text,
        parse_document,
        sha256_bytes,
    )
    from backend.services.intelligence import (
        analyze_document,
        compare_documents,
        summarize_document,
    )
    from backend.services.ollama_client import OllamaClient, OllamaConfig


class CompareRequest(BaseModel):
    left_document_id: str = Field(..., min_length=4)
    right_document_id: str = Field(..., min_length=4)


class ExportRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    format: str = Field(default="json")


app = FastAPI(
    title="Smart Document Intelligence Platform",
    version="2.0.0",
    description="Local-first document intelligence with FastAPI + Ollama + SQLite",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database(DB_PATH)
db.init_schema()
ollama = OllamaClient(
    OllamaConfig(
        base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, vision_model=OLLAMA_VISION_MODEL
    )
)


MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_version_group(value: str | None, filename: str) -> str:
    if value:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
        if normalized:
            return normalized
    base = Path(filename).stem.lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "document"


def parse_json_field(raw: str | None, fallback: Any) -> Any:
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def get_document_or_404(document_id: str) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM documents WHERE id = ?", (document_id,))
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Document not found: {document_id}"
        )
    return row


def latest_analysis(document_id: str, analysis_type: str) -> dict[str, Any] | None:
    record = db.fetch_one(
        """
        SELECT result_json, level, created_at
        FROM document_analyses
        WHERE document_id = ? AND analysis_type = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id, analysis_type),
    )
    if record is None:
        return None
    return {
        "result": parse_json_field(record.get("result_json"), {}),
        "level": record.get("level", ""),
        "created_at": record.get("created_at", ""),
    }


def list_entities(document_id: str) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT entity_type, entity_value, confidence, snippet, start_index, end_index
        FROM document_entities
        WHERE document_id = ?
        ORDER BY confidence DESC, entity_type, entity_value
        """,
        (document_id,),
    )
    return rows


def save_analysis(
    document_id: str, analysis_type: str, level: str, result: dict[str, Any]
) -> None:
    db.execute(
        """
        INSERT INTO document_analyses(document_id, analysis_type, level, result_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (document_id, analysis_type, level, json.dumps(result), now_iso()),
    )


def replace_entities(document_id: str, entities: list[dict[str, Any]]) -> None:
    db.execute("DELETE FROM document_entities WHERE document_id = ?", (document_id,))
    payload: list[tuple[Any, ...]] = []
    for entity in entities:
        payload.append(
            (
                document_id,
                str(entity.get("entity_type") or "unknown"),
                str(entity.get("value") or ""),
                float(entity.get("confidence", 0.0) or 0.0),
                str(entity.get("snippet") or ""),
                entity.get("start_index"),
                entity.get("end_index"),
                now_iso(),
            )
        )

    db.executemany(
        """
        INSERT INTO document_entities(
            document_id,
            entity_type,
            entity_value,
            confidence,
            snippet,
            start_index,
            end_index,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )


def store_chunks(document_id: str, text: str) -> None:
    db.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    chunks = chunk_text(text)
    payload = [(document_id, index, chunk) for index, chunk in enumerate(chunks)]
    db.executemany(
        "INSERT INTO document_chunks(document_id, chunk_index, content) VALUES (?, ?, ?)",
        payload,
    )


def format_document_row(row: dict[str, Any]) -> dict[str, Any]:
    auto_extract = latest_analysis(row["id"], "auto_extract")
    summary_brief = ""
    if auto_extract and isinstance(auto_extract["result"], dict):
        summary_brief = str(auto_extract["result"].get("summary_brief") or "")

    return {
        "id": row["id"],
        "filename": row["filename"],
        "file_type": row["file_type"],
        "file_size": row["file_size"],
        "uploaded_at": row["uploaded_at"],
        "preview_text": row["preview_text"],
        "version_group": row["version_group"],
        "version_number": row["version_number"],
        "analysis_status": row["analysis_status"],
        "summary_brief": summary_brief,
    }


def run_auto_analysis(document_row: dict[str, Any]) -> dict[str, Any]:
    path = Path(document_row["file_path"])
    image_bytes: list[bytes] | None = None
    if document_row["file_type"] in {"png", "jpg", "jpeg"} and path.exists():
        image_bytes = [path.read_bytes()]

    result = analyze_document(
        text=document_row["full_text"],
        filename=document_row["filename"],
        ollama=ollama,
        image_bytes=image_bytes,
    )
    save_analysis(document_row["id"], "auto_extract", "default", result)
    replace_entities(document_row["id"], result.get("entities", []))
    db.execute(
        "UPDATE documents SET analysis_status = ? WHERE id = ?",
        ("complete", document_row["id"]),
    )
    return result


def document_versions(document_id: str) -> list[dict[str, Any]]:
    document = get_document_or_404(document_id)
    rows = db.fetch_all(
        """
        SELECT id, filename, uploaded_at, version_number, parent_document_id
        FROM documents
        WHERE version_group = ?
        ORDER BY version_number ASC, uploaded_at ASC
        """,
        (document["version_group"],),
    )
    return rows


@app.get("/health")
def health() -> dict[str, Any]:
    ollama_health = ollama.health()
    doc_count = db.fetch_one("SELECT COUNT(*) AS count FROM documents") or {"count": 0}
    return {
        "status": "ok",
        "mode": "local-only",
        "version": "2.0.0",
        "ollama": ollama_health,
        "documents": doc_count["count"],
        "supported_types": list(SUPPORTED_EXTENSIONS.values()),
    }


@app.get("/dashboard")
def dashboard() -> dict[str, Any]:
    stats = {
        "documents": (db.fetch_one("SELECT COUNT(*) AS c FROM documents") or {"c": 0})[
            "c"
        ],
    }

    recent_documents = db.fetch_all(
        "SELECT * FROM documents ORDER BY uploaded_at DESC LIMIT 8"
    )
    return {
        "stats": stats,
        "recent_documents": [format_document_row(row) for row in recent_documents],
    }


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    version_group: str | None = Form(default=None),
    parent_document_id: str | None = Form(default=None),
    auto_analyze: bool = Form(default=True),
) -> dict[str, Any]:
    original_name = file.filename or "uploaded-file"
    extension = Path(original_name).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS.keys()))}",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds max upload size of {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )

    doc_id = uuid.uuid4().hex
    stored_path = UPLOAD_DIR / f"{doc_id}{extension}"
    stored_path.write_bytes(raw)

    file_type = SUPPORTED_EXTENSIONS[extension]
    checksum = sha256_bytes(raw)
    group = clean_version_group(version_group, original_name)

    if parent_document_id:
        _ = get_document_or_404(parent_document_id)

    max_version_row = db.fetch_one(
        "SELECT MAX(version_number) AS max_version FROM documents WHERE version_group = ?",
        (group,),
    )
    next_version = int(max_version_row.get("max_version") or 0) + 1

    try:
        extracted_text = parse_document(stored_path, file_type)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to process file: {exc}"
        ) from exc

    preview_text = (
        build_preview(extracted_text) if extracted_text else "No text extracted."
    )
    uploaded_at = now_iso()

    db.execute(
        """
        INSERT INTO documents(
            id,
            filename,
            file_path,
            file_type,
            file_size,
            checksum,
            uploaded_at,
            preview_text,
            full_text,
            version_group,
            version_number,
            parent_document_id,
            analysis_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            original_name,
            str(stored_path),
            file_type,
            len(raw),
            checksum,
            uploaded_at,
            preview_text,
            extracted_text,
            group,
            next_version,
            parent_document_id,
            "processing" if auto_analyze else "pending",
        ),
    )

    if extracted_text:
        store_chunks(doc_id, extracted_text)

    document = get_document_or_404(doc_id)

    auto_extract: dict[str, Any] | None = None
    if auto_analyze:
        try:
            auto_extract = run_auto_analysis(document)
        except Exception as exc:
            db.execute(
                "UPDATE documents SET analysis_status = ? WHERE id = ?",
                ("failed", doc_id),
            )
            auto_extract = {
                "summary_brief": "Automatic AI extraction failed.",
                "summary_detailed": str(exc),
                "bullet_points": [],
                "entities": [],
                "highlights": [],
            }

    return {
        "document": format_document_row(get_document_or_404(doc_id)),
        "analysis": auto_extract,
    }


@app.post("/upload")
async def legacy_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    response = await upload_document(file=file)
    document = response["document"]
    return {
        "document_id": document["id"],
        "filename": document["filename"],
        "pages": 0,
        "chars": len(get_document_or_404(document["id"])["full_text"]),
        "truncated": False,
    }


@app.get("/documents")
def list_documents() -> dict[str, Any]:
    rows = db.fetch_all("SELECT * FROM documents ORDER BY uploaded_at DESC")
    return {"documents": [format_document_row(row) for row in rows]}


@app.delete("/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, Any]:
    document = get_document_or_404(document_id)
    file_path = Path(document["file_path"])

    if file_path.exists():
        try:
            file_path.unlink()
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to delete file from disk: {exc}"
            ) from exc

    db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    return {"status": "deleted", "document_id": document_id}


@app.get("/documents/{document_id}")
def document_detail(document_id: str) -> dict[str, Any]:
    document = get_document_or_404(document_id)
    analyses_rows = db.fetch_all(
        """
        SELECT analysis_type, level, result_json, created_at
        FROM document_analyses
        WHERE document_id = ?
        ORDER BY created_at DESC
        """,
        (document_id,),
    )
    analyses = [
        {
            "analysis_type": row["analysis_type"],
            "level": row["level"],
            "created_at": row["created_at"],
            "result": parse_json_field(row["result_json"], {}),
        }
        for row in analyses_rows
    ]

    return {
        "document": format_document_row(document),
        "full_text": document["full_text"],
        "entities": list_entities(document_id),
        "analyses": analyses,
        "versions": document_versions(document_id),
    }


@app.get("/documents/{document_id}/file")
def read_document_file(document_id: str) -> FileResponse:
    document = get_document_or_404(document_id)
    file_path = Path(document["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists on disk.")

    media_type = (
        MEDIA_TYPES.get(document["file_type"])
        or mimetypes.guess_type(document["filename"])[0]
    )
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{document["filename"]}"'},
    )


@app.get("/documents/{document_id}/summary")
def get_summary(
    document_id: str,
    level: str = Query(default="brief", pattern="^(brief|detailed|bullets)$"),
) -> dict[str, Any]:
    document = get_document_or_404(document_id)

    existing = db.fetch_one(
        """
        SELECT result_json, created_at
        FROM document_analyses
        WHERE document_id = ? AND analysis_type = 'summary' AND level = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id, level),
    )
    if existing:
        return {
            "document_id": document_id,
            "summary": parse_json_field(existing["result_json"], {}),
            "created_at": existing["created_at"],
            "cached": True,
        }

    result = summarize_document(text=document["full_text"], level=level, ollama=ollama)
    save_analysis(document_id, "summary", level, result)
    return {
        "document_id": document_id,
        "summary": result,
        "created_at": now_iso(),
        "cached": False,
    }


@app.post("/documents/{document_id}/analyze")
def analyze_document_endpoint(document_id: str) -> dict[str, Any]:
    document = get_document_or_404(document_id)

    image_bytes: list[bytes] | None = None
    file_path = Path(document["file_path"])
    if document["file_type"] in {"png", "jpg", "jpeg"} and file_path.exists():
        image_bytes = [file_path.read_bytes()]

    result = analyze_document(
        text=document["full_text"],
        filename=document["filename"],
        ollama=ollama,
        image_bytes=image_bytes,
    )
    save_analysis(document_id, "auto_extract", "default", result)
    replace_entities(document_id, result.get("entities", []))
    db.execute(
        "UPDATE documents SET analysis_status = ? WHERE id = ?",
        ("complete", document_id),
    )
    return {"document_id": document_id, "analysis": result}


@app.get("/documents/{document_id}/versions")
def get_versions(document_id: str) -> dict[str, Any]:
    versions = document_versions(document_id)
    return {"document_id": document_id, "versions": versions}


@app.post("/compare")
def compare(payload: CompareRequest) -> dict[str, Any]:
    left = get_document_or_404(payload.left_document_id)
    right = get_document_or_404(payload.right_document_id)

    result = compare_documents(
        left_name=left["filename"],
        left_text=left["full_text"],
        right_name=right["filename"],
        right_text=right["full_text"],
        ollama=ollama,
    )
    save_analysis(left["id"], "comparison", "against:" + right["id"], result)

    return {
        "left_document": format_document_row(left),
        "right_document": format_document_row(right),
        "comparison": result,
    }


@app.post("/export")
def export_data(payload: ExportRequest) -> StreamingResponse:
    selected_ids = payload.document_ids
    if not selected_ids:
        selected_rows = db.fetch_all(
            "SELECT id FROM documents ORDER BY uploaded_at DESC"
        )
        selected_ids = [row["id"] for row in selected_rows]

    if not selected_ids:
        raise HTTPException(
            status_code=400, detail="No documents available for export."
        )

    placeholders = ",".join("?" for _ in selected_ids)
    docs = db.fetch_all(
        f"SELECT * FROM documents WHERE id IN ({placeholders}) ORDER BY uploaded_at DESC",
        tuple(selected_ids),
    )
    if not docs:
        raise HTTPException(status_code=404, detail="Selected documents not found.")

    entities = db.fetch_all(
        f"""
        SELECT document_id, entity_type, entity_value, confidence, snippet
        FROM document_entities
        WHERE document_id IN ({placeholders})
        ORDER BY document_id, confidence DESC
        """,
        tuple(selected_ids),
    )

    analysis_map: dict[str, dict[str, Any]] = {}
    for document in docs:
        latest = latest_analysis(document["id"], "auto_extract")
        analysis_map[document["id"]] = latest["result"] if latest else {}

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_format = payload.format.lower().strip()

    if export_format == "json":
        content = {
            "generated_at": now_iso(),
            "documents": [
                {
                    **format_document_row(doc),
                    "entities": [
                        row for row in entities if row["document_id"] == doc["id"]
                    ],
                    "analysis": analysis_map.get(doc["id"], {}),
                }
                for doc in docs
            ],
        }
        raw = json.dumps(content, indent=2).encode("utf-8")
        filename = f"document-export-{timestamp}.json"
        media_type = "application/json"

    elif export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "document_id",
                "filename",
                "version_group",
                "version_number",
                "entity_type",
                "entity_value",
                "confidence",
                "snippet",
                "summary_brief",
            ],
        )
        writer.writeheader()

        doc_by_id = {doc["id"]: doc for doc in docs}
        for entity in entities:
            doc = doc_by_id.get(entity["document_id"])
            if not doc:
                continue
            summary_brief = str(
                analysis_map.get(doc["id"], {}).get("summary_brief") or ""
            )
            writer.writerow(
                {
                    "document_id": doc["id"],
                    "filename": doc["filename"],
                    "version_group": doc["version_group"],
                    "version_number": doc["version_number"],
                    "entity_type": entity["entity_type"],
                    "entity_value": entity["entity_value"],
                    "confidence": entity["confidence"],
                    "snippet": entity["snippet"],
                    "summary_brief": summary_brief,
                }
            )

        raw = output.getvalue().encode("utf-8")
        filename = f"document-export-{timestamp}.csv"
        media_type = "text/csv"

    elif export_format == "report":
        lines: list[str] = [
            "# Smart Document Intelligence Report",
            "",
            f"Generated: {now_iso()}",
            "",
        ]
        for doc in docs:
            lines.append(f"## {doc['filename']} (v{doc['version_number']})")
            lines.append(f"- Document ID: `{doc['id']}`")
            lines.append(f"- Uploaded: {doc['uploaded_at']}")
            lines.append(f"- Version Group: `{doc['version_group']}`")

            analysis = analysis_map.get(doc["id"], {})
            if analysis:
                lines.append(f"- Brief Summary: {analysis.get('summary_brief', '')}")

            doc_entities = [
                entity for entity in entities if entity["document_id"] == doc["id"]
            ][:15]
            if doc_entities:
                lines.append("- Extracted Entities:")
                for entity in doc_entities:
                    lines.append(
                        f"  - [{entity['entity_type']}] {entity['entity_value']} (confidence {float(entity['confidence']):.2f})"
                    )

            lines.append("")

        raw = "\n".join(lines).encode("utf-8")
        filename = f"document-report-{timestamp}.md"
        media_type = "text/markdown"

    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported export format. Use json, csv, or report.",
        )

    return StreamingResponse(
        io.BytesIO(raw),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
