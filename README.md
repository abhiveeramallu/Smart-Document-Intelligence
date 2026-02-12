# Smart Document Intelligence Platform

A privacy-first, local-only document intelligence platform that transforms documents into actionable business insights using local AI (Ollama). No external APIs or cloud services required.

## 📊 Architecture

```mermaid
flowchart TB
    subgraph Frontend["🖥️ Frontend (React + Vite)"]
        UI[Document Intelligence UI]
        Upload[Upload Component]
        Workspace[Workspace Component]
        Compare[Compare Panel]
        Export[Export Panel]
    end
    
    subgraph Backend["⚙️ Backend (FastAPI + SQLite)"]
        API[REST API]
        DB[(SQLite Database)]
        Parser[Document Parser]
        Intelligence[AI Intelligence Engine]
        OllamaClient[Ollama Client]
    end
    
    subgraph AI["🤖 Local AI (Ollama)"]
        LLM[llama3.2 Model]
        Vision[Vision Model]
    end
    
    subgraph Storage["💾 Local Storage"]
        Files[Uploaded Files]
    end
    
    UI --> Upload
    UI --> Workspace
    UI --> Compare
    UI --> Export
    
    Upload --> API
    Workspace --> API
    Compare --> API
    Export --> API
    
    API --> DB
    API --> Parser
    API --> Intelligence
    
    Parser --> Files
    Intelligence --> OllamaClient
    OllamaClient --> LLM
    OllamaClient --> Vision
    
    DB --> API
    Files --> Parser
```

## 🔄 Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Parser
    participant AI
    participant DB
    
    User->>Frontend: Upload Document
    Frontend->>Backend: POST /documents/upload
    Backend->>Parser: Parse Document
    Parser-->>Backend: Extracted Text
    Backend->>AI: Analyze Document
    AI-->>Backend: Entities + Summary
    Backend->>DB: Store Results
    Backend-->>Frontend: Document + Analysis
    Frontend-->>User: Display Results
    
    User->>Frontend: Request Summary
    Frontend->>Backend: GET /documents/{id}/summary
    Backend->>DB: Check Cache
    alt Cache Miss
        Backend->>AI: Generate Summary
        AI-->>Backend: Summary Content
        Backend->>DB: Cache Result
    end
    Backend-->>Frontend: Summary
    Frontend-->>User: Display Summary
```

## 🗄️ Database Schema

```mermaid
erDiagram
    DOCUMENTS ||--o{ DOCUMENT_ANALYSES : has
    DOCUMENTS ||--o{ DOCUMENT_ENTITIES : contains
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : stores
    
    DOCUMENTS {
        string id PK
        string filename
        string file_path
        string file_type
        int file_size
        string checksum
        string uploaded_at
        string preview_text
        string full_text
        string version_group
        int version_number
        string parent_document_id
        string analysis_status
    }
    
    DOCUMENT_ANALYSES {
        int id PK
        string document_id FK
        string analysis_type
        string level
        string result_json
        string created_at
    }
    
    DOCUMENT_ENTITIES {
        int id PK
        string document_id FK
        string entity_type
        string entity_value
        float confidence
        string snippet
        int start_index
        int end_index
        string created_at
    }
    
    DOCUMENT_CHUNKS {
        int id PK
        string document_id FK
        int chunk_index
        string content
    }
```

## ✨ Features

- Upload `PDF`, `DOCX`, `TXT`, `PNG`, `JPG` files (drag/drop or picker)
- Automatic document analysis and entity extraction
- Summary generation (`brief`, `detailed`, `bullets`)
- Document version comparison (similarity percentage shown in UI)
- Export extracted data as `JSON`, `CSV`, or markdown report
- Remove documents (deletes file + related local records)

## Removed From Scope

These modules were intentionally removed from the project:
- Document Chat
- Conversations
- Template Extraction
- Automated Workflows
- Notifications
- Multi-Document Chat

## Project Structure

```text
pythonchatbott-main/
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── database.py
│   ├── services/
│   │   ├── document_parser.py
│   │   ├── intelligence.py
│   │   └── ollama_client.py
│   └── data/
│       ├── document_intel.db
│       └── uploads/
└── frontend/
    └── src/
        ├── App.jsx
        ├── App.css
        └── services/apiService.js
```

## API Endpoints

- `GET /health`
- `GET /dashboard`
- `POST /documents/upload`
- `POST /upload` (legacy compatibility)
- `GET /documents`
- `DELETE /documents/{document_id}`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/file`
- `GET /documents/{document_id}/summary?level=brief|detailed|bullets`
- `POST /documents/{document_id}/analyze`
- `GET /documents/{document_id}/versions`
- `POST /compare`
- `POST /export`

## Run Locally

### 1) Backend

```bash
cd /Users/vabhiram/Downloads/pythonchatbott-main
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Backend URL: `http://127.0.0.1:8000`

### 2) Ollama

Pull model:

```bash
ollama pull llama3.2:3b
```

Optional env vars:

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.2:3b
export OLLAMA_VISION_MODEL=llama3.2-vision
```

### 3) Frontend

```bash
cd /Users/vabhiram/Downloads/pythonchatbott-main/frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

Optional frontend env:

```bash
VITE_API_BASE=http://127.0.0.1:8000
```

## UI Notes (Current)

- Sidebar: upload + document library + remove action
- Main area: summary/extraction workspace
- Compare panel: similarity percentage
- Export panel: JSON/CSV/Report + manual download trigger
- No auto-download for document preview endpoint (`/documents/{id}/file` serves inline)

## Privacy

- Files are stored locally in `backend/data/uploads`
- Metadata, analyses, and entities are stored in local SQLite (`backend/data/document_intel.db`)
- AI inference is performed through local Ollama endpoint

## Troubleshooting

- `Error: listen tcp 127.0.0.1:11434: bind: address already in use`
  - Ollama is already running. Do not start a second `ollama serve`.
- `MLX: Failed to load symbol: mlx_metal_device_info`
  - Usually non-blocking if model pull/inference still works.
- Frontend still showing old UI
  - Restart `npm run dev` and hard refresh browser.

## Validation Commands

```bash
# backend syntax check
python3 -m compileall backend

# frontend production build
cd frontend && npm run build
```
