const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

function withTimeout(timeoutMs = 120000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  return {
    signal: controller.signal,
    clear: () => clearTimeout(timeout),
  };
}

async function parseResponse(response) {
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail = data?.detail || `Request failed (${response.status})`;
    throw new Error(detail);
  }

  return data;
}

export function getDocumentFileUrl(documentId) {
  return `${API_BASE}/documents/${documentId}/file`;
}

export async function checkHealth() {
  const timeout = withTimeout(15000);
  try {
    const response = await fetch(`${API_BASE}/health`, { signal: timeout.signal });
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function getDashboard() {
  const timeout = withTimeout(20000);
  try {
    const response = await fetch(`${API_BASE}/dashboard`, { signal: timeout.signal });
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function listDocuments() {
  const timeout = withTimeout(25000);
  try {
    const response = await fetch(`${API_BASE}/documents`, { signal: timeout.signal });
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function getDocument(documentId) {
  const timeout = withTimeout(30000);
  try {
    const response = await fetch(`${API_BASE}/documents/${documentId}`, {
      signal: timeout.signal,
    });
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function deleteDocument(documentId) {
  const timeout = withTimeout(30000);
  try {
    const response = await fetch(`${API_BASE}/documents/${documentId}`, {
      method: "DELETE",
      signal: timeout.signal,
    });
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function uploadDocument(file, { versionGroup = "", parentDocumentId = "", autoAnalyze = true } = {}) {
  const timeout = withTimeout(240000);
  const formData = new FormData();
  formData.append("file", file);
  if (versionGroup) {
    formData.append("version_group", versionGroup);
  }
  if (parentDocumentId) {
    formData.append("parent_document_id", parentDocumentId);
  }
  formData.append("auto_analyze", String(Boolean(autoAnalyze)));

  try {
    const response = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      body: formData,
      signal: timeout.signal,
    });
    return await parseResponse(response);
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("Upload timed out. Try a smaller file or faster local model.");
    }
    throw error;
  } finally {
    timeout.clear();
  }
}

export async function getSummary(documentId, level = "brief") {
  const timeout = withTimeout(90000);
  try {
    const response = await fetch(
      `${API_BASE}/documents/${documentId}/summary?level=${encodeURIComponent(level)}`,
      { signal: timeout.signal }
    );
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function compareDocuments(leftDocumentId, rightDocumentId) {
  const timeout = withTimeout(140000);
  try {
    const response = await fetch(`${API_BASE}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: timeout.signal,
      body: JSON.stringify({
        left_document_id: leftDocumentId,
        right_document_id: rightDocumentId,
      }),
    });
    return await parseResponse(response);
  } finally {
    timeout.clear();
  }
}

export async function exportData({ documentIds = [], format = "json" } = {}) {
  const timeout = withTimeout(120000);
  try {
    const response = await fetch(`${API_BASE}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: timeout.signal,
      body: JSON.stringify({ document_ids: documentIds, format }),
    });

    if (!response.ok) {
      let data = null;
      try {
        data = await response.json();
      } catch {
        data = null;
      }
      throw new Error(data?.detail || "Export failed.");
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
    const filename = filenameMatch ? filenameMatch[1] : `document-export.${format}`;

    return { blob, filename };
  } finally {
    timeout.clear();
  }
}
