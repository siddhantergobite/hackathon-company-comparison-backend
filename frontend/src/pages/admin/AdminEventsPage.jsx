import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Copy, ExternalLink, Pencil, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { adminApi, apiErrorMessage } from '../../api/events';
import { Banner, Button, Card, EmptyState, KpiGrid } from '../../components/ui';
import Pagination from '../../components/events/Pagination';
import EventPicker from '../../components/admin/EventPicker';
import { ReviewBadge } from '../../components/admin/AdminBits';
import { useAdminEventList, useDebounce } from '../../hooks/useEventData';
import { useToast } from '../../context/ToastContext';
import { formatDateRange, startCase } from '../../utils/events';

const REVIEW = [['', 'All review states'], ['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['duplicate', 'Duplicates']];
const STATUS = [['', 'Any status'], ['upcoming', 'Upcoming'], ['ongoing', 'Ongoing'], ['completed', 'Completed'], ['cancelled', 'Cancelled'], ['postponed', 'Postponed']];

export default function AdminEventsPage() {
  const toast = useToast();
  const [q, setQ] = useState('');
  const search = useDebounce(q, 350);
  const [review, setReview] = useState('');
  const [status, setStatus] = useState('');
  const [needsReview, setNeedsReview] = useState(false);
  const [page, setPage] = useState(1);
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState('');
  const [dupTarget, setDupTarget] = useState(null);

  const params = useMemo(
    () => ({ page, limit: 25, search: search || undefined, review_status: review || undefined, status: status || undefined, needs_review: needsReview || undefined, sort: 'recently_updated' }),
    [page, search, review, status, needsReview],
  );
  const { data, loading, error, reload } = useAdminEventList(params);

  useEffect(() => setPage(1), [search, review, status, needsReview]);
  const loadStats = useCallback(() => adminApi.stats().then(setStats).catch(() => {}), []);
  useEffect(() => { loadStats(); }, [loadStats]);

  const run = async (id, label, action) => {
    setBusy(id);
    try {
      await action();
      toast.success(label);
      reload();
      loadStats();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy('');
    }
  };

  const remove = (e) => {
    if (window.confirm(`Delete “${e.title}” permanently? This cannot be undone.`)) run(e.id, 'Event deleted.', () => adminApi.remove(e.id));
  };

  const events = data?.events || [];
  const kpis = stats
    ? [
        ['Total events', stats.total],
        ['Needs review', stats.needs_review],
        ['Approved', stats.by_review_status?.approved || 0],
        ['Pending', stats.by_review_status?.pending || 0],
        ['Errors (24h)', stats.ingestion_errors_24h],
      ]
    : [];

  return (
    <div className="stack stack--lg">
      <KpiGrid items={kpis} />

      <Card pad={false} className="adm-filters">
        <div className="input-wrap adm-filters__search">
          <Search size={17} aria-hidden="true" />
          <input className="input input--icon" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, city, organizer…" aria-label="Search events" />
        </div>
        <select className="input" value={review} onChange={(e) => setReview(e.target.value)} aria-label="Review status">
          {REVIEW.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Event status">
          {STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="adm-check">
          <input type="checkbox" checked={needsReview} onChange={(e) => setNeedsReview(e.target.checked)} /> Needs review
        </label>
      </Card>

      {error && <Banner tone="error" title="Unable to load events" action={<Button size="sm" variant="secondary" icon={RefreshCw} onClick={reload}>Try again</Button>}>{error}</Banner>}

      <Card flush pad={false}>
        <div className="table-wrap">
          <table className="table adm-table">
            <thead>
              <tr><th>Event</th><th>Date</th><th>Location</th><th>Source</th><th>Review</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className={busy === e.id ? 'is-busy' : ''}>
                  <td>
                    <div className="adm-title">{e.title}</div>
                    <div className="text-xs muted">{startCase(e.event_type)}{e.possible_duplicate_of ? ' · possible duplicate' : ''}{e.manually_edited ? ' · edited' : ''}</div>
                  </td>
                  <td className="nowrap">{formatDateRange(e.start_date, e.end_date)}</td>
                  <td>{[e.location?.city, e.location?.country].filter(Boolean).join(', ') || (e.is_online ? 'Online' : '—')}</td>
                  <td>{e.source?.name || '—'}</td>
                  <td><ReviewBadge value={e.review_status} /></td>
                  <td>{startCase(e.status)}</td>
                  <td>
                    <div className="adm-actions">
                      <Link className="icon-btn icon-btn--sm" to={`/admin/events/${e.id}/edit`} title="Edit" aria-label={`Edit ${e.title}`}><Pencil size={15} /></Link>
                      {e.review_status !== 'approved' && (
                        <button type="button" className="icon-btn icon-btn--sm" title="Approve" aria-label={`Approve ${e.title}`} onClick={() => run(e.id, 'Event approved.', () => adminApi.approve(e.id))}><Check size={15} /></button>
                      )}
                      {e.review_status !== 'rejected' && (
                        <button type="button" className="icon-btn icon-btn--sm" title="Reject" aria-label={`Reject ${e.title}`} onClick={() => run(e.id, 'Event rejected.', () => adminApi.reject(e.id))}><X size={15} /></button>
                      )}
                      <button type="button" className="icon-btn icon-btn--sm" title="Reprocess (re-clean and re-classify)" aria-label={`Reprocess ${e.title}`} onClick={() => run(e.id, 'Event reprocessed.', () => adminApi.reprocess(e.id))}><RefreshCw size={15} /></button>
                      <button type="button" className="icon-btn icon-btn--sm" title="Mark as duplicate of…" aria-label={`Mark ${e.title} as duplicate`} onClick={() => setDupTarget(e)}><Copy size={15} /></button>
                      {e.review_status === 'approved' && e.slug && (
                        <Link className="icon-btn icon-btn--sm" to={`/events/${e.slug}`} title="View public page" aria-label={`View ${e.title}`}><ExternalLink size={15} /></Link>
                      )}
                      <button type="button" className="icon-btn icon-btn--sm icon-btn--danger" title="Delete" aria-label={`Delete ${e.title}`} onClick={() => remove(e)}><Trash2 size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && !events.length && !error && (
          <EmptyState title="No events match">Try a different search or filter.</EmptyState>
        )}
      </Card>

      <Pagination page={data?.page || 1} totalPages={data?.total_pages || 0} onChange={setPage} disabled={loading} />

      <EventPicker
        open={Boolean(dupTarget)}
        title={dupTarget ? `“${dupTarget.title}” is a duplicate of…` : ''}
        excludeId={dupTarget?.id}
        onClose={() => setDupTarget(null)}
        onPick={(master) => {
          const target = dupTarget;
          setDupTarget(null);
          run(target.id, `Marked as a duplicate of “${master.title}”.`, () => adminApi.markDuplicate(target.id, master.id));
        }}
      />
    </div>
  );
}
