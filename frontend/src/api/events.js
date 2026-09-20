import axios from 'axios';

// Same origin by default (FastAPI serves the build; Vite proxies /api in dev).
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
const ADMIN_KEY_STORAGE = 'eventhub:adminKey';

export const http = axios.create({ baseURL: `${API_BASE}/api`, timeout: 30000 });

export const adminKey = {
  get() {
    try {
      return sessionStorage.getItem(ADMIN_KEY_STORAGE) || '';
    } catch {
      return '';
    }
  },
  set(key) {
    try {
      sessionStorage.setItem(ADMIN_KEY_STORAGE, key);
    } catch {
      /* storage blocked: the key just won't survive a reload */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(ADMIN_KEY_STORAGE);
    } catch {
      /* ignore */
    }
  },
};

// The admin key is attached to admin routes ONLY, never to public requests.
http.interceptors.request.use((config) => {
  if ((config.url || '').startsWith('/admin')) {
    const key = config.headers['X-Admin-Key'] || adminKey.get();
    if (key) config.headers['X-Admin-Key'] = key;
  }
  return config;
});

http.interceptors.response.use(
  (r) => r,
  (err) => {
    const isAdmin = (err.config?.url || '').startsWith('/admin');
    if (isAdmin && err.response?.status === 401 && !err.config?.skipAuthRedirect) {
      adminKey.clear();
      window.dispatchEvent(new Event('eventhub:auth-lost'));
    }
    return Promise.reject(err);
  },
);

export const isCancel = axios.isCancel;

export function apiErrorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (axios.isCancel(err)) return '';
  if (err.code === 'ECONNABORTED') return 'The request timed out. Please try again.';
  if (!err.response) return 'Cannot reach the server. Check your connection and that the backend is running.';
  const data = err.response.data;
  if (typeof data?.detail === 'string') {
    const extra = Array.isArray(data.errors) && data.errors.length ? `: ${data.errors.map((e) => `${e.field} ${e.message}`).join('; ')}` : '';
    return data.detail + extra;
  }
  return fallback;
}

const clean = (params = {}) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined));

// ------------------------------------------------------------------------------ public
export const eventsApi = {
  list: (params, signal) => http.get('/events', { params: clean(params), signal }).then((r) => r.data),
  bySlug: (slug, signal) => http.get(`/events/slug/${encodeURIComponent(slug)}`, { signal }).then((r) => r.data),
  types: () => http.get('/events/types').then((r) => r.data),
  categories: (params) => http.get('/events/categories', { params }).then((r) => r.data),
  locations: (params) => http.get('/events/locations', { params: clean(params) }).then((r) => r.data),
};

// ------------------------------------------------------------------------------- admin
export const adminApi = {
  // Used by the login form: a wrong key must show an error, not bounce back to the login screen.
  verify: (key) =>
    http.get('/admin/session', { headers: { 'X-Admin-Key': key }, skipAuthRedirect: true }).then((r) => r.data),
  stats: () => http.get('/admin/stats').then((r) => r.data),
  list: (params, signal) => http.get('/admin/events', { params: clean(params), signal }).then((r) => r.data),
  get: (id) => http.get(`/admin/events/${id}`).then((r) => r.data),
  create: (body) => http.post('/admin/events', body).then((r) => r.data),
  update: (id, body) => http.put(`/admin/events/${id}`, body).then((r) => r.data),
  remove: (id) => http.delete(`/admin/events/${id}`).then((r) => r.data),
  approve: (id) => http.post(`/admin/events/${id}/approve`).then((r) => r.data),
  reject: (id) => http.post(`/admin/events/${id}/reject`).then((r) => r.data),
  markDuplicate: (id, duplicateOf) => http.post(`/admin/events/${id}/duplicate`, { duplicate_of: duplicateOf }).then((r) => r.data),
  reprocess: (id, body = {}) => http.post(`/admin/events/${id}/reprocess`, body).then((r) => r.data),
  merge: (masterId, duplicateIds) => http.post('/admin/merge', { master_id: masterId, duplicate_ids: duplicateIds }).then((r) => r.data),
  duplicates: () => http.get('/admin/duplicates').then((r) => r.data),
  dismissDuplicate: (aId, bId) => http.post('/admin/duplicates/dismiss', { a_id: aId, b_id: bId }).then((r) => r.data),
  sources: () => http.get('/admin/sources').then((r) => r.data),
  runs: (params) => http.get('/admin/ingestion/runs', { params: clean(params) }).then((r) => r.data),
  errors: (params) => http.get('/admin/ingestion/errors', { params: clean(params) }).then((r) => r.data),
};
