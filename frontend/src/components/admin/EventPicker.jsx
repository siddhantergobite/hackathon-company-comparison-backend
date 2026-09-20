import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { adminApi, apiErrorMessage } from '../../api/events';
import { Banner, Modal } from '../ui';
import { formatDateRange } from '../../utils/events';
import { useDebounce } from '../../hooks/useEventData';
import { ReviewBadge } from './AdminBits';

// Modal to search for the "original" event when marking another one as its duplicate.
export default function EventPicker({ open, title, excludeId, onPick, onClose }) {
  const [q, setQ] = useState('');
  const debounced = useDebounce(q, 300);
  const [state, setState] = useState({ items: [], loading: false, error: '' });

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setState((s) => ({ ...s, loading: true, error: '' }));
    adminApi
      .list({ search: debounced, limit: 8, sort: 'recently_updated' })
      .then((d) => live && setState({ items: d.events.filter((e) => e.id !== excludeId && e.review_status !== 'duplicate'), loading: false, error: '' }))
      .catch((err) => live && setState({ items: [], loading: false, error: apiErrorMessage(err) }));
    return () => {
      live = false;
    };
  }, [open, debounced, excludeId]);

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="input-wrap">
        <Search size={17} aria-hidden="true" />
        <input className="input input--icon" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by title, city, organizer…" aria-label="Search events" autoFocus />
      </div>
      {state.error && <div style={{ marginTop: 12 }}><Banner tone="error">{state.error}</Banner></div>}
      <ul className="adm-picker">
        {state.items.map((e) => (
          <li key={e.id}>
            <button type="button" onClick={() => onPick(e)}>
              <strong>{e.title}</strong>
              <span className="muted text-sm">{formatDateRange(e.start_date, e.end_date)} · {e.location?.city || 'Online'} · {e.source?.name}</span>
              <ReviewBadge value={e.review_status} />
            </button>
          </li>
        ))}
        {!state.loading && !state.items.length && <li className="muted text-sm" style={{ padding: 12 }}>No matching events.</li>}
      </ul>
    </Modal>
  );
}
