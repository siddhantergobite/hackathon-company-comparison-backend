// Same-origin by default (FastAPI serves the build, Vite proxies /api in dev).
// Set VITE_API_BASE to point the UI at a backend on another origin.
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

function detailToMessage(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ') || fallback;
  }
  return JSON.stringify(detail);
}

async function send(path, options, fallbackMessage) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new Error('Cannot reach the backend. Check that it is running on port 8765.');
  }
  return { response, fallbackMessage };
}

async function postJson(path, body, fallbackMessage) {
  const { response } = await send(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    fallbackMessage,
  );
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* non-JSON error body */
  }
  if (!response.ok) throw new Error(detailToMessage(data?.detail, fallbackMessage));
  return data;
}

export const api = {
  brochureSearch: (companyName) =>
    postJson('/api/brochure-search', { company_name: companyName }, 'Search failed'),

  async brochureUpload(file) {
    const fd = new FormData();
    fd.append('file', file);
    const { response } = await send('/api/brochure-upload', { method: 'POST', body: fd });
    let data = null;
    try {
      data = await response.json();
    } catch {
      /* non-JSON error body */
    }
    if (!response.ok) throw new Error(detailToMessage(data?.detail, 'Upload failed'));
    return data;
  },

  companyResearch: (url) => postJson('/api/company-research', { url }, 'Research failed'),

  generatePitch: (brochure, target) =>
    postJson('/api/generate-pitch', { brochure, target }, 'Pitch failed'),

  aeoGeoAudit: (url, keywords) =>
    postJson(
      '/api/aeo-geo-audit',
      {
        url,
        keywords,
        use_serpapi: false,
        max_topics: keywords ? Math.min(keywords.length, 3) : 3,
      },
      'AEO/GEO audit failed',
    ),

  async exportPdf({ brochure, target, pitch, aeo }) {
    const { response } = await send('/api/export-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brochure, target, pitch, aeo }),
    });
    if (!response.ok) {
      let detail = null;
      try {
        detail = (await response.json()).detail;
      } catch {
        /* non-JSON error body */
      }
      throw new Error(detailToMessage(detail, 'PDF export failed'));
    }
    const blob = new Blob([await response.arrayBuffer()], { type: 'application/pdf' });
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    return { blob, filename: match ? match[1] : null };
  },
};
