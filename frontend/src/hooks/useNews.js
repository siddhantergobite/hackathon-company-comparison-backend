import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiErrorMessage, isCancel, newsApi } from '../api/news';
import { PAGE_SIZE, localDateBound, presetRange } from '../utils/news';

// Generic loader with cancellation, reload() and optional silent auto-refresh while the tab is visible.
export function useApi(fetcher, deps = [], { refreshMs = 0 } = {}) {
  const [state, setState] = useState({ data: null, loading: true, error: '' });
  const [nonce, setNonce] = useState(0);
  const ref = useRef(fetcher);
  ref.current = fetcher;

  useEffect(() => {
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: s.data === null, error: '' }));
    ref
      .current(controller.signal)
      .then((data) => setState({ data, loading: false, error: '' }))
      .catch((err) => {
        if (isCancel(err)) return;
        setState((s) => ({ data: s.data, loading: false, error: apiErrorMessage(err, 'Unable to load') }));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  useEffect(() => {
    if (!refreshMs) return undefined;
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') setNonce((n) => n + 1);
    }, refreshMs);
    return () => window.clearInterval(id);
  }, [refreshMs]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}

// --------------------------------------------------------------------------- feed (Load more)
export function useNewsFeed(params, { refreshMs = 0 } = {}) {
  const key = JSON.stringify(params);
  const [state, setState] = useState({ items: [], total: 0, page: 0, hasMore: false, loading: true, loadingMore: false, error: '' });
  const [nonce, setNonce] = useState(0);
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const inflight = useRef(null);

  useEffect(() => {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    setState((s) => ({ ...s, loading: true, error: '', ...(nonce === 0 ? { items: [] } : {}) }));
    newsApi
      .list({ ...paramsRef.current, page: 1, limit: PAGE_SIZE }, controller.signal)
      .then((d) => setState({ items: d.articles, total: d.total, page: d.page, hasMore: d.has_more, loading: false, loadingMore: false, error: '' }))
      .catch((err) => {
        if (isCancel(err)) return;
        setState((s) => ({ ...s, loading: false, error: apiErrorMessage(err, 'Unable to load news') }));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  const loadMore = useCallback(() => {
    setState((s) => {
      if (s.loadingMore || !s.hasMore) return s;
      const next = s.page + 1;
      const controller = new AbortController();
      inflight.current = controller;
      newsApi
        .list({ ...paramsRef.current, page: next, limit: PAGE_SIZE }, controller.signal)
        .then((d) =>
          setState((cur) => {
            const seen = new Set(cur.items.map((a) => a.id));
            return { ...cur, items: [...cur.items, ...d.articles.filter((a) => !seen.has(a.id))], total: d.total, page: d.page, hasMore: d.has_more, loadingMore: false };
          }),
        )
        .catch((err) => {
          if (isCancel(err)) return;
          setState((cur) => ({ ...cur, loadingMore: false, error: apiErrorMessage(err, 'Unable to load more') }));
        });
      return { ...s, loadingMore: true, error: '' };
    });
  }, []);

  useEffect(() => {
    if (!refreshMs) return undefined;
    const id = window.setInterval(() => {
      // Only refresh silently while the user is still on the first page.
      if (document.visibilityState === 'visible' && window.scrollY < 400) setNonce((n) => n + 1);
    }, refreshMs);
    return () => window.clearInterval(id);
  }, [refreshMs]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, loadMore, reload };
}

// ------------------------------------------------------------------------- URL-backed filters
export const DEFAULT_FILTERS = { category: 'all', q: '', source: '', topic: '', date: '', from: '', to: '', sort: 'latest' };

export function useNewsFilters() {
  const [sp, setSp] = useSearchParams();
  const filters = useMemo(() => Object.fromEntries(Object.entries(DEFAULT_FILTERS).map(([k, d]) => [k, sp.get(k) || d])), [sp]);

  const update = useCallback(
    (patch, { replace = false } = {}) => {
      const next = { ...DEFAULT_FILTERS, ...Object.fromEntries(Object.keys(DEFAULT_FILTERS).map((k) => [k, sp.get(k) || DEFAULT_FILTERS[k]])), ...patch };
      if ('date' in patch && patch.date !== 'custom') Object.assign(next, { from: '', to: '' });
      const out = new URLSearchParams();
      Object.entries(next).forEach(([k, v]) => {
        if (v && v !== DEFAULT_FILTERS[k]) out.set(k, v);
      });
      setSp(out, { replace });
    },
    [sp, setSp],
  );
  const clear = useCallback((keep = ['category']) => {
    const out = new URLSearchParams();
    keep.forEach((k) => sp.get(k) && out.set(k, sp.get(k)));
    setSp(out);
  }, [sp, setSp]);

  const activeCount = [filters.source, filters.topic, filters.date].filter(Boolean).length;
  return { filters, update, clear, activeCount };
}

export function toFeedParams(f) {
  let from = null;
  let to = null;
  if (f.date === 'custom') [from, to] = [localDateBound(f.from), localDateBound(f.to, true)];
  else if (f.date) [from, to] = presetRange(f.date);
  return {
    category: f.category && f.category !== 'all' ? f.category : undefined,
    q: f.q.trim() || undefined,
    source: f.source || undefined,
    topic: f.topic || undefined,
    from: from || undefined,
    to: to || undefined,
    sort: f.sort,
  };
}

export function useDebounced(value, delay = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);
  return v;
}
