import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminApi, apiErrorMessage, eventsApi, isCancel } from '../api/events';

export function useDebounce(value, delay = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);
  return v;
}

// Generic "load on params change" hook. Keeps the previous data on screen while the next
// page loads (no flash), cancels stale requests, and exposes reload().
function useLoader(fetcher, params) {
  const key = JSON.stringify(params);
  const [state, setState] = useState({ data: null, loading: true, error: '' });
  const [nonce, setNonce] = useState(0);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  useEffect(() => {
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: '' }));
    fetchRef
      .current(params, controller.signal)
      .then((data) => setState({ data, loading: false, error: '' }))
      .catch((err) => {
        if (isCancel(err)) return;
        setState((s) => ({ data: s.data, loading: false, error: apiErrorMessage(err, 'Unable to load events') }));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}

export const useEventList = (params) => useLoader(eventsApi.list, params);
export const useAdminEventList = (params) => useLoader(adminApi.list, params);

// Filter options: event types + categories once, and locations that depend on the chosen country/state.
export function useFacets(country, state) {
  const [facets, setFacets] = useState({ types: [], categories: [], locations: { countries: [], states: [], cities: [] } });

  useEffect(() => {
    let live = true;
    Promise.allSettled([eventsApi.types(), eventsApi.categories()]).then(([t, c]) => {
      if (!live) return;
      setFacets((f) => ({ ...f, types: t.value || [], categories: c.value || [] }));
    });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    let live = true;
    eventsApi
      .locations({ country, state })
      .then((locations) => live && setFacets((f) => ({ ...f, locations })))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [country, state]);

  return useMemo(() => facets, [facets]);
}
