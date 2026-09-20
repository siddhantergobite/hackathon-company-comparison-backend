import { useEffect, useState } from 'react';
import { adminApi, apiErrorMessage } from '../../api/events';
import { Banner, Card, CardHeader, LoadingPanel } from '../../components/ui';
import { HealthBadge, RunBadge, formatDateTime } from '../../components/admin/AdminBits';

const countsText = (c = {}) =>
  ['created', 'updated', 'merged', 'flagged', 'skipped', 'invalid', 'errors'].filter((k) => c[k]).map((k) => `${c[k]} ${k}`).join(' · ') || 'no changes';

export default function AdminSourcesPage() {
  const [state, setState] = useState({ sources: null, runs: [], error: '' });

  useEffect(() => {
    let live = true;
    Promise.all([adminApi.sources(), adminApi.runs({ limit: 15 })])
      .then(([sources, runs]) => live && setState({ sources, runs, error: '' }))
      .catch((err) => live && setState({ sources: [], runs: [], error: apiErrorMessage(err) }));
    return () => {
      live = false;
    };
  }, []);

  if (!state.sources) return <LoadingPanel title="Loading source health…" />;
  if (state.error) return <Banner tone="error" title="Unable to load source health">{state.error}</Banner>;

  return (
    <div className="stack stack--lg">
      <Card flush pad={false}>
        <div style={{ padding: '20px 24px 0' }}><CardHeader title="Sources" /></div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Source</th><th>Health</th><th>Events</th><th>Errors (24h)</th><th>Last run</th></tr></thead>
            <tbody>
              {state.sources.map((s) => (
                <tr key={s.name}>
                  <td>
                    <div className="adm-title">{s.label}</div>
                    <div className="text-xs muted">{s.description}</div>
                    {s.health === 'not_configured' && <div className="text-xs muted"><code>{s.name}</code> — add its credentials/feed in <code>.env</code> or <code>sources.json</code></div>}
                  </td>
                  <td><HealthBadge value={s.health} /></td>
                  <td>{s.events}</td>
                  <td>{s.errors_24h}</td>
                  <td>
                    {s.last_run ? (
                      <>
                        <RunBadge value={s.last_run.status} /> <span className="text-sm">{formatDateTime(s.last_run.started_at)}</span>
                        <div className="text-xs muted">{countsText(s.last_run.counts)}</div>
                        {s.last_run.error && <div className="text-xs con">{s.last_run.error}</div>}
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card flush pad={false}>
        <div style={{ padding: '20px 24px 0' }}><CardHeader title="Recent ingestion runs" /></div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Source</th><th>Started</th><th>Status</th><th>Result</th></tr></thead>
            <tbody>
              {state.runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.label || r.source}</td>
                  <td className="nowrap">{formatDateTime(r.started_at)}</td>
                  <td><RunBadge value={r.status} /></td>
                  <td className="text-sm">{countsText(r.counts)}{r.error ? <div className="con text-xs">{r.error}</div> : null}</td>
                </tr>
              ))}
              {!state.runs.length && <tr><td colSpan={4} className="muted">No ingestion runs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="text-sm muted">
        Run a source from the project root: <code>python -m backend.events.scripts.ingest_events --list</code>, then <code>--source NAME</code> (add <code>--dry-run</code> to preview).
      </p>
    </div>
  );
}
