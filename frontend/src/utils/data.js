// Helpers for the loosely-typed JSON the research backend returns.
// Fields can be strings, numbers, arrays, or {value, source, confidence} objects.

export function asArray(v) {
  return Array.isArray(v) ? v : [];
}

export function flattenVal(v, depth = 0) {
  if (v == null || v === '') return '';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'string') {
    const s = v.trim();
    if (!s || s.toLowerCase() === '[object object]') return '';
    return s;
  }
  if (depth > 4) return '';
  if (Array.isArray(v)) {
    return v
      .map((x) => flattenVal(x, depth + 1))
      .filter(Boolean)
      .join(', ');
  }
  if (typeof v === 'object') {
    if ('value' in v) return flattenVal(v.value, depth + 1);
    for (const k of ['text', 'label', 'name', 'summary', 'regions', 'countries', 'description', 'item']) {
      if (v[k] != null && v[k] !== '') return flattenVal(v[k], depth + 1);
    }
    return Object.entries(v)
      .filter(([k]) => !['source', 'confidence', 'verified', 'favicon', 'provenance'].includes(k))
      .map(([, x]) => flattenVal(x, depth + 1))
      .filter(Boolean)
      .join('; ');
  }
  return '';
}

export function val(field) {
  if (field && typeof field === 'object' && 'value' in field) return flattenVal(field.value);
  return flattenVal(field);
}

// Normalises 0–1 fractions, 0–100 numbers and words like "high" to a 0–100 score.
export function scoreNum(v) {
  if (typeof v === 'number' && Number.isFinite(v)) {
    if (v > 0 && v <= 1) return Math.round(v * 100);
    return Math.round(v);
  }
  const s = String(v || '').trim().toLowerCase();
  const map = { 'very high': 90, high: 80, medium: 60, med: 60, low: 35, 'very low': 20 };
  if (Object.prototype.hasOwnProperty.call(map, s)) return map[s];
  const n = parseFloat(String(v));
  if (!Number.isFinite(n)) return null;
  if (n > 0 && n <= 1) return Math.round(n * 100);
  return Math.max(0, Math.min(100, Math.round(n)));
}

// For scores that are already on a 0–100 scale (a value of 1 means 1, not 100%).
export function percentScore(v) {
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, Math.round(n)));
}

// Scraped pages sometimes leak UI chrome / boilerplate into extracted fields.
export function isJunkText(s) {
  const t = String(s || '').toLowerCase();
  if (!t) return true;
  return /what's on your mind|create images|ai mode|add images|add files|forgot password|sign in|cookie|captcha|google offered in|request has been blocked|skip to main content|jump to content|main menu|move to sidebar|chatgpt|chat\.openai|what can i help with|message chatgpt|upgrade to plus|authenticity \d|source reliability \d|omitted rather than guessed|not independently verified/.test(
    t,
  );
}

export function hasData(v) {
  let x = v;
  if (x && typeof x === 'object' && !Array.isArray(x)) x = flattenVal(x);
  if (!x) return false;
  const s = String(x).trim().toLowerCase();
  return Boolean(
    s &&
      !s.includes('not publicly') &&
      !s.includes('not available') &&
      s !== 'n/a' &&
      s !== '—' &&
      s !== '[object object]',
  );
}

export function pointOf(item) {
  if (!item) return '';
  if (typeof item === 'string') return item;
  return item.point || item.value || item.name || item.title || item.item || '';
}

export function riskText(field) {
  if (!field) return '';
  if (typeof field === 'string') return field;
  if (Array.isArray(field)) {
    return field
      .map((item) => (typeof item === 'string' ? item : item.risk || item.point || item.value || ''))
      .filter(Boolean)
      .join('; ');
  }
  if (typeof field === 'object') return field.risk || field.point || field.value || '';
  return String(field);
}

export function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

export function ensureUrl(u) {
  if (!u) return '#';
  const s = String(u).trim();
  if (s.startsWith('http://') || s.startsWith('https://')) return s;
  return 'https://' + s.replace(/^\/\//, '');
}

export function citeHref(c) {
  const url = (c && (c.url || c.source_url || c.href)) || '';
  if (url && /^https?:\/\//i.test(url)) return url;
  const domain = c && c.domain ? String(c.domain).replace(/^www\./, '') : '';
  if (domain && domain.includes('.')) return 'https://' + domain;
  return ensureUrl(url);
}

export function isHistoricalLeader(leader) {
  const role = leader.role || leader.title || '';
  return (
    leader.status === 'historical' ||
    (/historical|former|co-?founder/i.test(role) &&
      !/ceo|chief executive|president|managing director/i.test(role))
  );
}
