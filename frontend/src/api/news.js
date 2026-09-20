import { http } from './events';

export { apiErrorMessage, isCancel } from './events';

const clean = (params = {}) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false));

// ------------------------------------------------------------------------------ public
export const newsApi = {
  list: (params, signal) => http.get('/news', { params: clean(params), signal }).then((r) => r.data),
  article: (id, signal) => http.get(`/news/${encodeURIComponent(id)}`, { signal }).then((r) => r.data),
  related: (id, limit = 8, signal) => http.get(`/news/related/${encodeURIComponent(id)}`, { params: { limit }, signal }).then((r) => r.data),
  story: (id, signal) => http.get(`/news/story/${encodeURIComponent(id)}`, { signal }).then((r) => r.data),
  topStories: (limit = 5, signal) => http.get('/news/top-stories', { params: { limit }, signal }).then((r) => r.data.articles),
  trending: (limit = 10, signal) => http.get('/news/trending', { params: { limit }, signal }).then((r) => r.data.articles),
  happening: (perGroup = 3, signal) => http.get('/news/whats-happening', { params: { per_group: perGroup }, signal }).then((r) => r.data.groups),
  categories: (signal) => http.get('/news/categories', { signal }).then((r) => r.data),
  sources: (signal) => http.get('/news/sources', { signal }).then((r) => r.data),
  topics: (limit = 24, signal) => http.get('/news/topics', { params: { limit }, signal }).then((r) => r.data),
};

// ------------------------------------------------------------------------------- admin
export const newsAdminApi = {
  verify: (key) => http.get('/admin/news/session', { headers: { 'X-Admin-Key': key }, skipAuthRedirect: true }).then((r) => r.data),
  stats: () => http.get('/admin/news/stats').then((r) => r.data),
  sources: () => http.get('/admin/news/sources').then((r) => r.data),
  createSource: (body) => http.post('/admin/news/sources', body).then((r) => r.data),
  updateSource: (id, body) => http.put(`/admin/news/sources/${encodeURIComponent(id)}`, body).then((r) => r.data),
  setEnabled: (id, enabled) => http.post(`/admin/news/sources/${encodeURIComponent(id)}/enabled`, { enabled }).then((r) => r.data),
  deleteSource: (id) => http.delete(`/admin/news/sources/${encodeURIComponent(id)}`).then((r) => r.data),
  fetchNow: (id) => http.post(`/admin/news/sources/${encodeURIComponent(id)}/fetch`, null, { timeout: 120000 }).then((r) => r.data),
  enrich: (limit = 10) => http.post('/admin/news/enrich', null, { params: { limit }, timeout: 180000 }).then((r) => r.data),
  recluster: (hours = 72) => http.post('/admin/news/recluster', null, { params: { hours }, timeout: 120000 }).then((r) => r.data),
  categories: () => http.get('/admin/news/categories').then((r) => r.data),
  createCategory: (body) => http.post('/admin/news/categories', body).then((r) => r.data),
  updateCategory: (slug, body) => http.put(`/admin/news/categories/${encodeURIComponent(slug)}`, body).then((r) => r.data),
  runs: (params) => http.get('/admin/news/runs', { params: clean(params) }).then((r) => r.data),
  errors: (params) => http.get('/admin/news/errors', { params: clean(params) }).then((r) => r.data),
};
