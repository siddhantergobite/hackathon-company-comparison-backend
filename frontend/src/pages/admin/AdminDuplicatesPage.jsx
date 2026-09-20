import { useCallback, useEffect, useState } from 'react';
import { CopyCheck, GitMerge } from 'lucide-react';
import { adminApi, apiErrorMessage } from '../../api/events';
import { Banner, Button, Card, EmptyState, LoadingPanel, Tag } from '../../components/ui';
import { ReviewBadge } from '../../components/admin/AdminBits';
import { useToast } from '../../context/ToastContext';
import { formatDateRange } from '../../utils/events';

function Side({ label, e }) {
  return (
    <div className="adm-dup__side">
      <div className="field-label">{label}</div>
      <div className="adm-title">{e.title}</div>
      <div className="text-sm muted">{formatDateRange(e.start_date, e.end_date)}</div>
      <div className="text-sm muted">{[e.location?.venue, e.location?.city, e.location?.country].filter(Boolean).join(', ') || 'Online / no location'}</div>
      <div className="text-sm muted">Organizer: {e.organizer?.name || '—'}</div>
      <div className="row" style={{ marginTop: 6 }}>
        <Tag tone="neutral">{e.source?.name || 'unknown source'}</Tag>
        <ReviewBadge value={e.review_status} />
      </div>
    </div>
  );
}

export default function AdminDuplicatesPage() {
  const toast = useToast();
  const [state, setState] = useState({ items: [], loading: true, error: '' });
  const [busy, setBusy] = useState('');

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: '' }));
    adminApi
      .duplicates()
      .then((items) => setState({ items, loading: false, error: '' }))
      .catch((err) => setState({ items: [], loading: false, error: apiErrorMessage(err) }));
  }, []);
  useEffect(load, [load]);

  const act = async (key, message, action) => {
    setBusy(key);
    try {
      await action();
      toast.success(message);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy('');
    }
  };

  if (state.loading && !state.items.length) return <LoadingPanel title="Scanning for duplicates…" />;
  if (state.error) return <Banner tone="error" title="Unable to load duplicates">{state.error}</Banner>;
  if (!state.items.length) {
    return <EmptyState icon={CopyCheck} title="No suspected duplicates">Events that look like the same event from different sources will appear here for review.</EmptyState>;
  }

  return (
    <div className="stack">
      <p className="muted">Pairs that look like the same event. <strong>Merge</strong> keeps one record, fills its gaps from the other and redirects the old link. <strong>Not duplicates</strong> dismisses the pair for good.</p>
      {state.items.map((d) => {
        const key = `${d.a.id}:${d.b.id}`;
        const disabled = busy === key;
        return (
          <Card key={key}>
            <div className="adm-dup__head">
              <Tag tone={d.confidence === 'high' ? 'red' : 'amber'}>{Math.round(d.score * 100)}% match · {d.confidence}</Tag>
              <span className="text-sm muted">{d.reasons.join(' · ')}</span>
            </div>
            <div className="adm-dup__pair">
              <Side label="Event A" e={d.a} />
              <Side label="Event B" e={d.b} />
            </div>
            <div className="adm-dup__actions">
              <Button size="sm" icon={GitMerge} disabled={disabled} onClick={() => act(key, 'Merged into A.', () => adminApi.merge(d.a.id, [d.b.id]))}>Keep A, merge B into it</Button>
              <Button size="sm" icon={GitMerge} disabled={disabled} onClick={() => act(key, 'Merged into B.', () => adminApi.merge(d.b.id, [d.a.id]))}>Keep B, merge A into it</Button>
              <Button size="sm" variant="secondary" disabled={disabled} onClick={() => act(key, 'Marked as different events.', () => adminApi.dismissDuplicate(d.a.id, d.b.id))}>Not duplicates</Button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
