import { useState } from 'react';
import { CircleCheck } from 'lucide-react';
import { newsAdminApi } from '../../../api/news';
import { Banner, Card, CardHeader, EmptyState, LoadingPanel, Tag } from '../../../components/ui';
import { RunBadge } from '../../../components/admin/AdminBits';
import { formatDateTime } from '../../../components/admin/AdminBits';
import { useApi } from '../../../hooks/useNews';

const counts = (c = {}) => ['created', 'clustered', 'updated', 'skipped', 'invalid', 'errors'].filter((k) => c[k]).map((k) => `${c[k]} ${k}`).join(' · ') || 'no changes';

export default function NewsErrorsPage() {
  const [source, setSource] = useState('');
  const sources = useApi(() => newsAdminApi.sources(), []);
  const errors = useApi(() => newsAdminApi.errors({ limit: 100, source: source || undefined }), [source], { refreshMs: 30_000 });
  const runs = useApi(() => newsAdminApi.runs({ limit: 30, source: source || undefined }), [source], { refreshMs: 30_000 });

  if (errors.loading && !errors.data) return <LoadingPanel title="Loading errors…" />;
  return (
    <div className="stack stack--lg">
      <div className="row">
        <label className="form-label" htmlFor="err-src" style={{ margin: 0 }}>Source</label>
        <select id="err-src" className="input" style={{ width: 'auto' }} value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources</option>
          {(sources.data || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      {errors.error && <Banner tone="error">{errors.error}</Banner>}

      {!errors.error && !(errors.data || []).length ? (
        <EmptyState icon={CircleCheck} title="No ingestion errors">Failed fetches, invalid items and AI problems are listed here (kept for 14 days).</EmptyState>
      ) : (
        <Card flush pad={false}>
          <div style={{ padding: '20px 24px 0' }}><CardHeader title="Recent errors" /></div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>When</th><th>Source</th><th>Type</th><th>Item</th><th>Problem</th></tr></thead>
              <tbody>
                {(errors.data || []).map((e) => (
                  <tr key={e.id}>
                    <td className="nowrap">{formatDateTime(e.created_at)}</td>
                    <td>{e.source_name || '—'}</td>
                    <td><Tag tone={e.type === 'validation' ? 'amber' : e.type === 'ai' ? 'neutral' : 'red'}>{e.type}</Tag></td>
                    <td className="text-sm">{e.record || '—'}</td>
                    <td className="text-sm">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card flush pad={false}>
        <div style={{ padding: '20px 24px 0' }}><CardHeader title="Recent runs" /></div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Source</th><th>Started</th><th>Status</th><th>Result</th></tr></thead>
            <tbody>
              {(runs.data || []).map((r) => (
                <tr key={r.id}>
                  <td>{r.source_name}</td>
                  <td className="nowrap">{formatDateTime(r.started_at)}</td>
                  <td><RunBadge value={r.status} /></td>
                  <td className="text-sm">{counts(r.counts)}{r.error && <div className="con text-xs">{r.error}</div>}</td>
                </tr>
              ))}
              {!(runs.data || []).length && <tr><td colSpan={4} className="muted">No runs recorded yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
