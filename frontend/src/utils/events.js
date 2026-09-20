// Formatting + filter helpers for the Event Hub UI.

const pad = (n) => String(n).padStart(2, '0');

// "2026-10-12" -> local Date (avoids the UTC shift of new Date('2026-10-12')).
export function parseYmd(s) {
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export const toYmd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const MON = MONTHS.map((m) => m.slice(0, 3));

// 12–14 October 2026 · 28 Oct – 2 Nov 2026 · 30 Dec 2026 – 2 Jan 2027
export function formatDateRange(start, end) {
  const a = parseYmd(start);
  if (!a) return 'Date to be announced';
  const b = parseYmd(end) || a;
  if (toYmd(a) === toYmd(b)) return `${a.getDate()} ${MONTHS[a.getMonth()]} ${a.getFullYear()}`;
  if (a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()) {
    return `${a.getDate()}–${b.getDate()} ${MONTHS[a.getMonth()]} ${a.getFullYear()}`;
  }
  if (a.getFullYear() === b.getFullYear()) {
    return `${a.getDate()} ${MON[a.getMonth()]} – ${b.getDate()} ${MON[b.getMonth()]} ${a.getFullYear()}`;
  }
  return `${a.getDate()} ${MON[a.getMonth()]} ${a.getFullYear()} – ${b.getDate()} ${MON[b.getMonth()]} ${b.getFullYear()}`;
}

export function formatLongDate(ymd) {
  const d = parseYmd(ymd);
  if (!d) return null;
  return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

export function formatIsoDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function formatLocation(event) {
  const loc = event.location || {};
  const place = [loc.city, loc.country].filter(Boolean).join(', ');
  if (event.format === 'online' || (event.is_online && !place)) return 'Online';
  if (event.format === 'hybrid') return place ? `${place} + Online` : 'Hybrid';
  return place || 'Location to be announced';
}

export function formatFormat(event) {
  if (event.format === 'hybrid') return 'Hybrid';
  if (event.format === 'online' || event.is_online) return 'Online';
  return 'In person';
}

export function formatPrice(reg = {}) {
  if (reg.ticket_type === 'free') return 'Free';
  if (reg.price != null && reg.price > 0) {
    try {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: reg.currency || 'USD', maximumFractionDigits: 0 }).format(reg.price);
    } catch {
      return `${reg.price} ${reg.currency || ''}`.trim();
    }
  }
  if (reg.ticket_type === 'paid') return 'Paid';
  return null;
}

export const startCase = (s) => String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export const STATUS_LABEL = { upcoming: 'Upcoming', ongoing: 'Happening now', completed: 'Ended', cancelled: 'Cancelled', postponed: 'Postponed' };

// ------------------------------------------------------------------------------- filters
export function presetRange(key, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (key === 'today') return [toYmd(today), toYmd(today)];
  if (key === 'week') {
    const end = new Date(today);
    end.setDate(today.getDate() + ((7 - today.getDay()) % 7)); // through Sunday
    return [toYmd(today), toYmd(end)];
  }
  if (key === 'month') return [toYmd(today), toYmd(new Date(today.getFullYear(), today.getMonth() + 1, 0))];
  if (key === 'next_month') {
    return [toYmd(new Date(today.getFullYear(), today.getMonth() + 1, 1)), toYmd(new Date(today.getFullYear(), today.getMonth() + 2, 0))];
  }
  return [null, null];
}

export const DATE_PRESETS = [
  { value: '', label: 'Any date' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'This week' },
  { value: 'month', label: 'This month' },
  { value: 'next_month', label: 'Next month' },
  { value: 'custom', label: 'Custom range' },
];

export const SORT_OPTIONS = [
  { value: 'soonest', label: 'Soonest first' },
  { value: 'latest', label: 'Latest first' },
  { value: 'recently_added', label: 'Recently added' },
  { value: 'recently_updated', label: 'Recently updated' },
];

export const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------------- maps
export function osmEmbedUrl(lat, lon) {
  const dLon = 0.012;
  const dLat = 0.007;
  const bbox = [lon - dLon, lat - dLat, lon + dLon, lat + dLat].map((n) => n.toFixed(5)).join('%2C');
  return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat}%2C${lon}`;
}

export const osmLink = (lat, lon) => `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=15/${lat}/${lon}`;

// Only ever navigate to http(s) URLs coming from the API.
export function safeUrl(u) {
  try {
    const p = new URL(u);
    return p.protocol === 'http:' || p.protocol === 'https:' ? p.href : null;
  } catch {
    return null;
  }
}
