// Thin wrapper around the Stage 1 backend endpoints. No auth, no
// database on either side of this call — see backend README.

const API_BASE = "http://127.0.0.1:8000";

export async function fetchHealth() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
  return response.json();
}

export async function fetchPdfPageCount(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/pdf/page-count`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await safeJson(response);
    throw new Error(body?.detail || `Page count failed: ${response.status}`);
  }
  return response.json();
}

export async function parsePage(file, pageNumber) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("page_number", String(pageNumber ?? 1));
  const response = await fetch(`${API_BASE}/parse`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await safeJson(response);
    throw new Error(body?.detail || `Parse failed: ${response.status}`);
  }
  return response.json();
}

// Milestone 3: parse a short run of consecutive PDF pages and get back
// cross-page continuity sections alongside each page's own extraction.
export async function parsePages(file, startPage, endPage) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("start_page", String(startPage));
  formData.append("end_page", String(endPage));
  const response = await fetch(`${API_BASE}/parse/pages`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await safeJson(response);
    throw new Error(body?.detail || `Parse pages failed: ${response.status}`);
  }
  return response.json();
}

// Final Phase: build full-book curriculum hierarchy and export ChessMethod JSON
export async function buildCurriculum(file, startPage, endPage, bookTitle) {
  const formData = new FormData();
  formData.append("file", file);
  if (startPage != null) formData.append("start_page", String(startPage));
  if (endPage != null) formData.append("end_page", String(endPage));
  if (bookTitle) formData.append("book_title", bookTitle);
  const response = await fetch(`${API_BASE}/build-curriculum`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await safeJson(response);
    throw new Error(body?.detail || `Build curriculum failed: ${response.status}`);
  }
  return response.json();
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
