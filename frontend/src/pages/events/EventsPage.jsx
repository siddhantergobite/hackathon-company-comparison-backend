import { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarSearch, RefreshCw, Search, SlidersHorizontal, X } from 'lucide-react';
import { Banner, Button, EmptyState, Modal, PageHeader } from '../../components/ui';
import EventCard, { EventCardSkeleton } from '../../components/events/EventCard';
import FilterPanel from '../../components/events/FilterPanel';
import ActiveFilters from '../../components/events/ActiveFilters';
import Pagination from '../../components/events/Pagination';
import { toApiParams, useEventFilters } from '../../hooks/useEventFilters';
import { useDebounce, useEventList, useFacets } from '../../hooks/useEventData';
import { PAGE_SIZE, SORT_OPTIONS } from '../../utils/events';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

export default function EventsPage() {
  useDocumentTitle('Events');
  const { filters, update, clear, activeCount } = useEventFilters();
  const facets = useFacets(filters.country, filters.state);
  const { data, loading, error, reload } = useEventList(useMemo(() => toApiParams(filters), [filters]));
  const [drawer, setDrawer] = useState(false);
  const topRef = useRef(null);

  // Search box: typing is debounced into the URL; URL changes made elsewhere (clear, Back) flow back in.
  const [text, setText] = useState(filters.q);
  const debounced = useDebounce(text, 350);
  const lastPushed = useRef(filters.q);
  useEffect(() => {
    if (debounced !== lastPushed.current) {
      lastPushed.current = debounced;
      update({ q: debounced }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  useEffect(() => {
    if (filters.q !== lastPushed.current) {
      lastPushed.current = filters.q;
      setText(filters.q);
    }
  }, [filters.q]);

  const typeLabels = useMemo(() => Object.fromEntries(facets.types.map((t) => [t.value, t.label])), [facets.types]);
  const events = data?.events || [];
  const total = data?.total ?? 0;
  const firstLoad = loading && !data;
  const from = total ? (data.page - 1) * data.limit + 1 : 0;
  const to = total ? from + events.length - 1 : 0;

  const goToPage = (page) => {
    update({ page });
    topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const clearAll = () => {
    setText('');
    lastPushed.current = '';
    clear();
  };

  return (
    <>
      <PageHeader
        eyebrow="Event Hub"
        title="Discover upcoming events"
        description="Conferences, meetups, seminars, startup and networking events from around the world — search, filter and open any event for the full details."
      />

      <div className="ev-toolbar" ref={topRef}>
        <div className="input-wrap ev-toolbar__search">
          <Search size={17} aria-hidden="true" />
          <input
            className="input input--icon"
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search events, organizers, cities, topics…"
            aria-label="Search events"
          />
          {text && (
            <button type="button" className="ev-toolbar__clear" onClick={() => setText('')} aria-label="Clear search">
              <X size={16} />
            </button>
          )}
        </div>
        <label className="ev-toolbar__sort">
          <span className="sr-only">Sort events</span>
          <select className="input" value={filters.sort} onChange={(e) => update({ sort: e.target.value })} aria-label="Sort events">
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <Button variant="secondary" className="ev-toolbar__filters" icon={SlidersHorizontal} onClick={() => setDrawer(true)}>
          Filters{activeCount ? ` (${activeCount})` : ''}
        </Button>
      </div>

      <div className="ev-layout">
        <aside className="ev-layout__filters" aria-label="Filters">
          <FilterPanel filters={filters} update={update} facets={facets} activeCount={activeCount} onClear={clearAll} />
        </aside>

        <section className="ev-layout__results" aria-busy={loading}>
          <ActiveFilters filters={filters} update={update} typeLabels={typeLabels} onClear={clearAll} />

          <div className="ev-results-head" aria-live="polite">
            {firstLoad ? (
              <span className="muted">Loading events…</span>
            ) : total ? (
              <span>
                Showing <strong>{from}–{to}</strong> of <strong>{total.toLocaleString()}</strong> event{total === 1 ? '' : 's'}
              </span>
            ) : (
              !error && <span className="muted">No events</span>
            )}
          </div>

          {error && (
            <Banner
              tone="error"
              title="Unable to load events"
              action={
                <Button size="sm" variant="secondary" icon={RefreshCw} onClick={reload}>
                  Try again
                </Button>
              }
            >
              {error}
            </Banner>
          )}

          {firstLoad && (
            <div className="ev-grid">
              {Array.from({ length: 6 }, (_, i) => (
                <EventCardSkeleton key={i} />
              ))}
            </div>
          )}

          {!firstLoad && !error && !events.length && (
            <EmptyState
              icon={CalendarSearch}
              title="No events found"
              action={
                (activeCount > 0 || filters.q) && (
                  <Button variant="secondary" onClick={clearAll}>
                    Clear search &amp; filters
                  </Button>
                )
              }
            >
              {filters.q || activeCount ? 'Nothing matches your search and filters. Try removing a filter or using different keywords.' : 'There are no upcoming events yet. Check back soon.'}
            </EmptyState>
          )}

          {events.length > 0 && (
            <div className={`ev-grid ${loading ? 'is-loading' : ''}`}>
              {events.map((e) => (
                <EventCard key={e.id} event={e} typeLabels={typeLabels} />
              ))}
            </div>
          )}

          <Pagination page={data?.page || 1} totalPages={data?.total_pages || 0} onChange={goToPage} disabled={loading} />
          {total > 0 && data?.total_pages > 1 && <p className="ev-pagination__note">Page {data.page} of {data.total_pages} · {PAGE_SIZE} events per page</p>}
        </section>
      </div>

      <Modal
        open={drawer}
        onClose={() => setDrawer(false)}
        title="Filters"
        footer={
          <Button onClick={() => setDrawer(false)}>{total ? `Show ${total.toLocaleString()} event${total === 1 ? '' : 's'}` : 'Show results'}</Button>
        }
      >
        <FilterPanel filters={filters} update={update} facets={facets} activeCount={activeCount} onClear={clearAll} />
      </Modal>
    </>
  );
}
