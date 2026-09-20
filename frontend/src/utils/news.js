// Formatting + filter helpers for the News UI.

const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

export function timeAgo(value, now = Date.now()) {
  if (!value) return '';
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Math.max(0, now - t);
  if (diff < MIN) return 'just now';
  if (diff < HOUR) {
    const m = Math.floor(diff / MIN);
    return `${m} minute${m === 1 ? '' : 's'} ago`;
  }
  if (diff < DAY) {
    const h = Math.floor(diff / HOUR);
    return `${h} hour${h === 1 ? '' : 's'} ago`;
  }
  if (diff < 2 * DAY) return 'yesterday';
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)} days ago`;
  return new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function formatDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// A story is "trending" when several outlets cover it or its score is high.
export const isTrending = (a) => (a.coverage?.count || 1) >= 3 || (a.trending_score || 0) >= 140;

export const sourceCount = (a) => a.coverage?.count || 1;

// ----------------------------------------------------------------------------- date filter
export const DATE_PRESETS = [
  { value: '', label: 'Any time' },
  { value: 'hour', label: 'Last hour' },
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'week', label: 'Last 7 days' },
  { value: 'custom', label: 'Custom range' },
];

export function presetRange(key, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (key === 'hour') return [new Date(now.getTime() - HOUR).toISOString(), null];
  if (key === 'today') return [startOfToday.toISOString(), null];
  if (key === 'yesterday') {
    const from = new Date(startOfToday.getTime() - DAY);
    return [from.toISOString(), new Date(startOfToday.getTime() - 1).toISOString()];
  }
  if (key === 'week') return [new Date(now.getTime() - 7 * DAY).toISOString(), null];
  return [null, null];
}

// A YYYY-MM-DD from a date input becomes a local-time bound.
export function localDateBound(ymd, end = false) {
  if (!ymd) return null;
  const [y, m, d] = ymd.split('-').map(Number);
  return (end ? new Date(y, m - 1, d, 23, 59, 59, 999) : new Date(y, m - 1, d)).toISOString();
}

export const SORTS = [
  { value: 'latest', label: 'Latest' },
  { value: 'trending', label: 'Trending' },
  { value: 'importance', label: 'Most important' },
];

export const PAGE_SIZE = 12;

export function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

// Only ever navigate to http(s) URLs coming from the API.
export function safeHref(u) {
  try {
    const p = new URL(u);
    return p.protocol === 'http:' || p.protocol === 'https:' ? p.href : null;
  } catch {
    return null;
  }
}

export const CATEGORY_HUE = {
  ai: 262, technology: 214, world: 200, india: 28, business: 160, finance: 142, startups: 330, science: 190, space: 240,
  cybersecurity: 0, politics: 350, economy: 90, health: 170, climate: 120, sports: 20, entertainment: 300, education: 50, travel: 180,
};
