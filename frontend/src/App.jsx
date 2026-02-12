import { useEffect, useMemo, useState } from "react";

import {
  checkHealth,
  compareDocuments,
  deleteDocument,
  exportData,
  getDashboard,
  getDocument,
  getSummary,
  listDocuments,
  uploadDocument,
} from "./services/apiService";

function formatDate(dateValue) {
  if (!dateValue) {
    return "-";
  }
  try {
    return new Date(dateValue).toLocaleString();
  } catch {
    return dateValue;
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [status, setStatus] = useState("Loading local services...");
  const [dashboard, setDashboard] = useState(null);

  const [documents, setDocuments] = useState([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [documentDetail, setDocumentDetail] = useState(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const [dragActive, setDragActive] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [versionGroupInput, setVersionGroupInput] = useState("");

  const [summaryLevel, setSummaryLevel] = useState("brief");
  const [summaryResult, setSummaryResult] = useState(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  const [compareTargetId, setCompareTargetId] = useState("");
  const [compareResult, setCompareResult] = useState(null);
  const [isComparing, setIsComparing] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState("");

  const [activeEntity, setActiveEntity] = useState(null);
  const [preparedExport, setPreparedExport] = useState(null);

  useEffect(() => {
    let ignore = false;

    async function bootstrap() {
      try {
        const [healthRes, dashboardRes, docsRes] = await Promise.all([
          checkHealth(),
          getDashboard(),
          listDocuments(),
        ]);

        if (ignore) {
          return;
        }

        setDashboard(dashboardRes);
        setDocuments(docsRes.documents || []);

        if (docsRes.documents?.length > 0) {
          setSelectedDocumentId(docsRes.documents[0].id);
        }

        const ollamaStatus = healthRes?.ollama?.available ? "connected" : "offline";
        setStatus(`System ready. Ollama: ${ollamaStatus}.`);
      } catch (error) {
        if (!ignore) {
          setStatus(`Startup error: ${error.message}`);
        }
      }
    }

    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedDocumentId) {
      setDocumentDetail(null);
      return;
    }

    let ignore = false;
    setIsLoadingDetail(true);

    async function loadDetail() {
      try {
        const detail = await getDocument(selectedDocumentId);
        if (!ignore) {
          setDocumentDetail(detail);
          setActiveEntity(null);
          setSummaryResult(null);
        }
      } catch (error) {
        if (!ignore) {
          setStatus(`Document load failed: ${error.message}`);
        }
      } finally {
        if (!ignore) {
          setIsLoadingDetail(false);
        }
      }
    }

    loadDetail();

    return () => {
      ignore = true;
    };
  }, [selectedDocumentId]);

  const selectedDocument = useMemo(
    () => documents.find((doc) => doc.id === selectedDocumentId) || null,
    [documents, selectedDocumentId]
  );

  const groupedEntities = useMemo(() => {
    const entities = documentDetail?.entities || [];
    const groups = new Map();
    for (const entity of entities) {
      if (!groups.has(entity.entity_type)) {
        groups.set(entity.entity_type, []);
      }
      groups.get(entity.entity_type).push(entity);
    }
    return Array.from(groups.entries());
  }, [documentDetail]);

  const analyzedCount = useMemo(
    () => documents.filter((doc) => doc.analysis_status === "complete").length,
    [documents]
  );
  const versionGroupCount = useMemo(
    () => new Set(documents.map((doc) => doc.version_group)).size,
    [documents]
  );
  const imageDocCount = useMemo(
    () => documents.filter((doc) => ["png", "jpg", "jpeg"].includes(doc.file_type)).length,
    [documents]
  );

  const similarityPercent = compareResult
    ? `${(Number(compareResult.similarity || 0) * 100).toFixed(1)}%`
    : "--";

  async function refreshAll({ keepSelected = true } = {}) {
    try {
      const [dashboardRes, docsRes] = await Promise.all([getDashboard(), listDocuments()]);
      const nextDocuments = docsRes.documents || [];

      setDashboard(dashboardRes);
      setDocuments(nextDocuments);

      if (!keepSelected) {
        setSelectedDocumentId(nextDocuments[0]?.id || "");
        return;
      }

      if (selectedDocumentId && !nextDocuments.some((doc) => doc.id === selectedDocumentId)) {
        setSelectedDocumentId(nextDocuments[0]?.id || "");
      }
    } catch (error) {
      setStatus(`Refresh failed: ${error.message}`);
    }
  }

  async function handleUpload(fileOverride = null) {
    const file = fileOverride || selectedFile;
    if (!file || isUploading) {
      return;
    }

    setIsUploading(true);
    setStatus(`Uploading ${file.name}...`);

    try {
      const result = await uploadDocument(file, {
        versionGroup: versionGroupInput.trim(),
      });

      const uploadedDoc = result.document;
      setSelectedFile(null);
      setVersionGroupInput("");
      setSelectedDocumentId(uploadedDoc.id);

      await refreshAll({ keepSelected: true });
      setStatus(`Uploaded ${uploadedDoc.filename}.`);
    } catch (error) {
      setStatus(`Upload failed: ${error.message}`);
    } finally {
      setIsUploading(false);
    }
  }

  async function handleSummaryLoad() {
    if (!selectedDocumentId || isLoadingSummary) {
      return;
    }

    setIsLoadingSummary(true);
    try {
      const result = await getSummary(selectedDocumentId, summaryLevel);
      setSummaryResult(result.summary);
    } catch (error) {
      setStatus(`Summary failed: ${error.message}`);
    } finally {
      setIsLoadingSummary(false);
    }
  }

  async function handleCompare() {
    if (!selectedDocumentId || !compareTargetId || isComparing) {
      return;
    }

    setIsComparing(true);
    try {
      const result = await compareDocuments(selectedDocumentId, compareTargetId);
      setCompareResult(result.comparison);
    } catch (error) {
      setStatus(`Comparison failed: ${error.message}`);
    } finally {
      setIsComparing(false);
    }
  }

  async function handleExport(format) {
    try {
      const docIds = selectedDocumentId ? [selectedDocumentId] : [];
      const { blob, filename } = await exportData({ documentIds: docIds, format });
      setPreparedExport({ blob, filename });
      setStatus(`Prepared ${filename}.`);
    } catch (error) {
      setStatus(`Export failed: ${error.message}`);
    }
  }

  async function handleDeleteDocument(documentId) {
    if (!documentId || deletingDocumentId) {
      return;
    }

    const target = documents.find((doc) => doc.id === documentId);
    const filename = target?.filename || "this document";
    const confirmed = window.confirm(
      `Remove "${filename}"? This deletes the file and extracted data from your local system.`
    );
    if (!confirmed) {
      return;
    }

    setDeletingDocumentId(documentId);
    try {
      await deleteDocument(documentId);

      const remaining = documents.filter((doc) => doc.id !== documentId);
      setDocuments(remaining);

      if (selectedDocumentId === documentId) {
        setSelectedDocumentId(remaining[0]?.id || "");
        setDocumentDetail(null);
        setSummaryResult(null);
        setActiveEntity(null);
      }

      if (compareTargetId === documentId) {
        setCompareTargetId("");
      }
      setCompareResult(null);
      setPreparedExport(null);
      setStatus(`Removed ${filename}.`);

      await refreshAll({ keepSelected: true });
    } catch (error) {
      setStatus(`Remove failed: ${error.message}`);
    } finally {
      setDeletingDocumentId("");
    }
  }

  function handleDownloadPreparedExport() {
    if (!preparedExport) {
      return;
    }
    downloadBlob(preparedExport.blob, preparedExport.filename);
  }

  function onFileInputChange(event) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
  }

  function onDrop(event) {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) {
      setSelectedFile(file);
      handleUpload(file);
    }
  }

  function onDragOver(event) {
    event.preventDefault();
    if (!dragActive) {
      setDragActive(true);
    }
  }

  function onDragLeave(event) {
    event.preventDefault();
    setDragActive(false);
  }

  return (
    <div className="app-shell">
      <div className="background-overlay" aria-hidden="true" />

      <aside className="sidebar panel">
        <div className="brand-block">
          <p className="brand-kicker">Enterprise Suite</p>
          <h1>Document Intelligence Platform</h1>
        </div>

        <section className="upload-panel">
          <div className="panel-head">
            <h3>Upload</h3>
          </div>

          <label
            className={`upload-zone ${dragActive ? "drag" : ""}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            <input
              type="file"
              accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
              onChange={onFileInputChange}
              disabled={isUploading}
            />
            <span>{isUploading ? "Processing..." : "Drop or choose files"}</span>
            <small>PDF, DOCX, TXT, PNG, JPG</small>
          </label>

          <div className="upload-actions">
            <input
              type="text"
              placeholder="Version group"
              value={versionGroupInput}
              onChange={(event) => setVersionGroupInput(event.target.value)}
              disabled={isUploading}
            />
            <button
              type="button"
              className="action-button"
              onClick={() => handleUpload()}
              disabled={!selectedFile || isUploading}
            >
              {isUploading ? "Uploading" : "Upload"}
            </button>
          </div>

          <p className="helper">{selectedFile ? `Selected: ${selectedFile.name}` : "No file selected"}</p>
        </section>

        <section className="library-panel">
          <div className="panel-head">
            <h3>Documents</h3>
            <span>{documents.length}</span>
          </div>

          <div className="library-scroll">
            {documents.length === 0 ? <p className="empty">No documents uploaded.</p> : null}
            {documents.map((doc) => (
              <div key={doc.id} className="doc-row">
                <button
                  type="button"
                  className={`doc-card ${selectedDocumentId === doc.id ? "active" : ""}`}
                  onClick={() => setSelectedDocumentId(doc.id)}
                >
                  <strong>{doc.filename}</strong>
                  <p>
                    {doc.file_type.toUpperCase()} • v{doc.version_number} • {doc.analysis_status}
                  </p>
                </button>

                <button
                  type="button"
                  className="action-button danger"
                  onClick={() => handleDeleteDocument(doc.id)}
                  disabled={deletingDocumentId === doc.id}
                >
                  {deletingDocumentId === doc.id ? "Removing" : "Remove"}
                </button>
              </div>
            ))}
          </div>
        </section>
      </aside>

      <main className="main-grid">
        <section id="hero" className="hero panel">
          <div>
            <p className="eyebrow">SMART DOCUMENT INTELLIGENCE</p>
            <h2>Transform documents into accurate, actionable business insights.</h2>
            <p className="hero-status">{status}</p>
          </div>
        </section>

        <section className="metrics">
          <article className="metric panel">
            <p>Documents</p>
            <h3>{dashboard?.stats?.documents ?? documents.length}</h3>
          </article>
          <article className="metric panel">
            <p>Analyzed</p>
            <h3>{analyzedCount}</h3>
          </article>
          <article className="metric panel">
            <p>Version Groups</p>
            <h3>{versionGroupCount}</h3>
          </article>
          <article className="metric panel">
            <p>Image Docs</p>
            <h3>{imageDocCount}</h3>
          </article>
        </section>

        <section id="workspace" className="workspace panel">
          <div className="panel-head">
            <h3>Summary & Extraction</h3>
          </div>

          {!selectedDocument ? (
            <p className="empty">Select a document to analyze.</p>
          ) : isLoadingDetail ? (
            <p className="empty">Loading document details...</p>
          ) : (
            <>
              <p className="workspace-title">{selectedDocument.filename}</p>
              <p>
                Uploaded {formatDate(selectedDocument.uploaded_at)} • Group {selectedDocument.version_group}
              </p>

              <div className="summary-controls">
                <select value={summaryLevel} onChange={(event) => setSummaryLevel(event.target.value)}>
                  <option value="brief">Brief</option>
                  <option value="detailed">Detailed</option>
                  <option value="bullets">Bullets</option>
                </select>
                <button
                  type="button"
                  className="action-button"
                  onClick={handleSummaryLoad}
                  disabled={isLoadingSummary}
                >
                  {isLoadingSummary ? "Generating" : "Generate"}
                </button>
              </div>

              <div className="summary-output">
                {summaryResult ? <p>{summaryResult.content}</p> : <p className="empty">No summary generated.</p>}
              </div>

              <div className="entity-grid">
                {groupedEntities.length === 0 ? <p className="empty">No entities extracted.</p> : null}
                {groupedEntities.map(([type, entities]) => (
                  <div key={type} className="entity-cluster">
                    <h4>{type}</h4>
                    <div className="chip-row">
                      {entities.slice(0, 10).map((entity, idx) => (
                        <button
                          key={`${type}-${idx}-${entity.entity_value}`}
                          type="button"
                          className="entity-chip"
                          onClick={() => setActiveEntity(entity)}
                        >
                          {entity.entity_value}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {activeEntity ? (
                <div className="highlight-block">
                  <p>{activeEntity.snippet || activeEntity.entity_value}</p>
                  <small>Confidence: {Number(activeEntity.confidence || 0).toFixed(2)}</small>
                </div>
              ) : null}
            </>
          )}
        </section>

        <section className="side-column">
          <article id="compare" className="compare panel">
            <div className="panel-head">
              <h3>Compare</h3>
            </div>

            <select value={compareTargetId} onChange={(event) => setCompareTargetId(event.target.value)}>
              <option value="">Select second document</option>
              {documents
                .filter((doc) => doc.id !== selectedDocumentId)
                .map((doc) => (
                  <option key={`cmp-${doc.id}`} value={doc.id}>
                    {doc.filename} (v{doc.version_number})
                  </option>
                ))}
            </select>

            <button
              type="button"
              className="action-button"
              onClick={handleCompare}
              disabled={!compareTargetId || !selectedDocumentId || isComparing}
            >
              {isComparing ? "Comparing" : "Run Compare"}
            </button>

            <div className="similarity-block">
              <p>Similarity</p>
              <h3>{similarityPercent}</h3>
            </div>
          </article>

          <article id="exports" className="exports panel">
            <div className="panel-head">
              <h3>Export</h3>
            </div>

            <div className="export-grid">
              <button
                type="button"
                className="action-button secondary"
                onClick={() => handleExport("json")}
                disabled={!selectedDocumentId}
              >
                JSON
              </button>
              <button
                type="button"
                className="action-button secondary"
                onClick={() => handleExport("csv")}
                disabled={!selectedDocumentId}
              >
                CSV
              </button>
              <button
                type="button"
                className="action-button secondary"
                onClick={() => handleExport("report")}
                disabled={!selectedDocumentId}
              >
                Report
              </button>
              <button
                type="button"
                className="action-button"
                onClick={handleDownloadPreparedExport}
                disabled={!preparedExport}
              >
                Download
              </button>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
