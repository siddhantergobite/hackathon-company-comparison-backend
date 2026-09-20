import { useEffect, useState } from 'react';
import { CircleCheck } from 'lucide-react';
import { adminApi, apiErrorMessage } from '../../api/events';
import { Banner, Card, EmptyState, LoadingPanel, Tag } from '../../components/ui';
import { formatDateTime } from '../../components/admin/AdminBits';

export default function AdminErrorsPage() {
  const [source, setSource] = useState('');
  const [sources, setSources] = useState([]);
  const [state, setState] = useState({ items: null, error: '' });

  useEffect(() => {
    adminApi.sources().then((s) => setSources(s.filter((x) => x.health !== 'manual').map((x) => x.name))).catch(() => {});
  }, []);

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, error: '' }));
    adminApi
      .errors({ limit: 100, source: source || undefined })
      .then((items) => live && setState({ items, error: '' }))
      .catch((err) => live && setState({ items: [], error: apiErrorMessage(err) }));
    return () => {
      live = false;
    };
  }, [source]);

  if (!state.items && !state.error) return <LoadingPanel title="Loading ingestion errors…" />;
  return (
    <div className="stack">
      <div className="row">
        <label className="form-label" htmlFor="err-source" style={{ margin: 0 }}>Source</label>
        <select id="err-source" className="input" style={{ width: 'auto' }} value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources</option>
          {sources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {state.error && <Banner tone="error" title="Unable to load errors">{state.error}</Banner>}
      {!state.error && !state.items.length && (
        <EmptyState icon={CircleCheck} title="No ingestion errors">Records that fail validation or sources that can't be reached are listed here.</EmptyState>
      )}
      {state.items?.length > 0 && (
        <Card flush pad={false}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>When</th><th>Source</th><th>Type</th><th>Record</th><th>Problem</th></tr></thead>
              <tbody>
                {state.items.map((e) => (
                  <tr key={e.id}>
                    <td className="nowrap">{formatDateTime(e.created_at)}</td>
                    <td>{e.source}</td>
                    <td><Tag tone={e.error_type === 'validation' ? 'amber' : 'red'}>{e.error_type}</Tag></td>
                    <td>{e.record || '—'}</td>
                    <td>
                      <div className="text-sm">{e.message}</div>
                      {e.raw && (
                        <details className="text-xs"><summary>Raw record</summary><pre className="code-block">{e.raw}</pre></details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
