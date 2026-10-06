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

async function postJson(path, body, fallbackMessage, requestOptions = {}) {
  const { response } = await send(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      ...requestOptions,
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

async function streamJson(path, body, onEvent, fallbackMessage, signal) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal,
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new Error('Cannot reach the backend. Check that it is running on port 8765.');
  }

  if (!response.ok) {
    let data = null;
    try {
      data = await response.json();
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detailToMessage(data?.detail, fallbackMessage));
  }

  if (!response.body) {
    const result = await response.json();
    onEvent?.({ type: 'complete', result });
    return result;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed = null;

  const consume = (text) => {
    buffer += text;
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      let event;
      try {
        event = JSON.parse(line);
      } catch {
        throw new Error('The backend sent an invalid live-results update.');
      }
      if (event.type === 'error') {
        throw new Error(detailToMessage(event.detail, fallbackMessage));
      }
      if (event.type === 'complete') completed = event.result;
      onEvent?.(event);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    consume(decoder.decode(value, { stream: true }));
  }
  consume(decoder.decode());
  if (!completed) throw new Error('The live-results stream ended before completion.');
  return completed;
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

  companyResearch: (url) =>
    postJson('/api/company-research', { url }, 'Research failed', { cache: 'no-store' }),

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

  async talentBench() {
    const { response } = await send('/api/talent-bench', { method: 'GET' }, 'Could not load talent bench');
    let data = null;
    try {
      data = await response.json();
    } catch {
      /* non-JSON */
    }
    if (!response.ok) throw new Error(detailToMessage(data?.detail, 'Could not load talent bench'));
    return data;
  },

  async talentUpload(file, slotId) {
    const fd = new FormData();
    fd.append('file', file);
    const q = slotId ? `?slot_id=${encodeURIComponent(slotId)}` : '';
    const { response } = await send(
      `/api/talent-bench/upload${q}`,
      { method: 'POST', body: fd },
    );
    let data = null;
    try {
      data = await response.json();
    } catch {
      /* non-JSON */
    }
    if (!response.ok) throw new Error(detailToMessage(data?.detail, 'Resume upload failed'));
    return data;
  },

  async talentClear(slotId) {
    const { response } = await send(`/api/talent-bench/${encodeURIComponent(slotId)}`, { method: 'DELETE' });
    let data = null;
    try {
      data = await response.json();
    } catch {
      /* non-JSON */
    }
    if (!response.ok) throw new Error(detailToMessage(data?.detail, 'Could not clear resume'));
    return data;
  },

  liveJobsScan: (filters = {}) =>
    postJson('/api/live-jobs/scan', {
      minutes: 30,
      sources: ['linkedin', 'naukri'],
      include_unverified_recent: true,
      skills: filters.skills || [],
      locations: filters.locations || [],
    }, 'Job scan failed'),

  liveJobsScanStream: (filters = {}, onEvent, signal) =>
    streamJson('/api/live-jobs/scan/stream', {
      minutes: 30,
      sources: ['linkedin', 'naukri'],
      include_unverified_recent: true,
      skills: filters.skills || [],
      locations: filters.locations || [],
    }, onEvent, 'Job scan failed', signal),

  liveJobsIngest: (url) =>
    postJson('/api/live-jobs/ingest', { url, days: 14 }, 'Could not load jobs from that URL'),

  liveJobsIngestStream: (url, onEvent, signal) =>
    streamJson('/api/live-jobs/ingest/stream', { url, days: 14 }, onEvent, 'Could not load jobs from that URL', signal),

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
