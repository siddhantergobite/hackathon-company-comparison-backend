import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PAGE_SIZE, presetRange } from '../utils/events';

export const DEFAULT_FILTERS = {
  q: '', type: [], category: [], country: '', state: '', city: '',
  format: '', price: '', date: '', from: '', to: '', sort: 'soonest', page: 1,
};

const csv = (v) => (v ? v.split(',').map((s) => s.trim()).filter(Boolean) : []);

function parse(sp) {
  const page = parseInt(sp.get('page') || '1', 10);
  return {
    q: sp.get('q') || '',
    type: csv(sp.get('type')),
    category: csv(sp.get('category')),
    country: sp.get('country') || '',
    state: sp.get('state') || '',
    city: sp.get('city') || '',
    format: sp.get('format') || '',
    price: sp.get('price') || '',
    date: sp.get('date') || '',
    from: sp.get('from') || '',
    to: sp.get('to') || '',
    sort: sp.get('sort') || 'soonest',
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

function serialize(f) {
  const sp = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    const isDefault = JSON.stringify(v) === JSON.stringify(DEFAULT_FILTERS[k]);
    if (isDefault || v === '' || (Array.isArray(v) && !v.length)) return;
    sp.set(k, Array.isArray(v) ? v.join(',') : String(v));
  });
  return sp;
}

// Filters live in the URL, so results are shareable and Back/Forward work.
export function useEventFilters() {
  const [sp, setSp] = useSearchParams();
  const filters = useMemo(() => parse(sp), [sp]);

  const update = useCallback(
    (patch, { replace = false } = {}) => {
      const next = { ...parse(sp), ...patch };
      if (!('page' in patch)) next.page = 1;
      if ('country' in patch && patch.country !== parse(sp).country) Object.assign(next, { state: '', city: '' });
      if ('state' in patch && patch.state !== parse(sp).state && !('city' in patch)) next.city = '';
      if ('date' in patch && patch.date !== 'custom') Object.assign(next, { from: '', to: '' });
      setSp(serialize(next), { replace });
    },
    [sp, setSp],
  );

  const clear = useCallback(() => setSp(new URLSearchParams()), [setSp]);

  // number of active filters, excluding search/sort/page
  const activeCount = useMemo(() => {
    const f = filters;
    return f.type.length + f.category.length + [f.country, f.state, f.city, f.format, f.price, f.date].filter(Boolean).length;
  }, [filters]);

  return { filters, update, clear, activeCount };
}

export function toApiParams(f) {
  let start = null;
  let end = null;
  if (f.date === 'custom') [start, end] = [f.from || null, f.to || null];
  else if (f.date) [start, end] = presetRange(f.date);
  return {
    page: f.page,
    limit: PAGE_SIZE,
    search: f.q.trim() || undefined,
    event_type: f.type.join(',') || undefined,
    category: f.category.join(',') || undefined,
    country: f.country || undefined,
    state: f.country ? f.state || undefined : undefined,
    city: f.country ? f.city || undefined : undefined,
    format: f.format || undefined,
    price_type: f.price || undefined,
    start_date: start || undefined,
    end_date: end || undefined,
    sort: f.sort,
  };
}
