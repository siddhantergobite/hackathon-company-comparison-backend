import { useMemo, useState } from 'react';
import { Layers, Pencil, Play, Plus, Power, RefreshCw, Search, Sparkles, Trash2 } from 'lucide-react';
import { apiErrorMessage, newsAdminApi } from '../../../api/news';
import { Banner, Button, Card, KpiGrid, LoadingPanel } from '../../../components/ui';
import { useApi } from '../../../hooks/useNews';
import { useToast } from '../../../context/ToastContext';
import { timeAgo } from '../../../utils/news';
import SourceForm from './SourceForm';

const HEALTH = {
  active: ['🟢', 'Active', 'ok'], failed: ['🔴', 'Failed', 'bad'], stale: ['🟡', 'Stale', 'warn'],
  never: ['⚪', 'Not fetched yet', 'muted'], disabled: ['⚫', 'Disabled', 'muted'],
};

function Status({ s }) {
  const [dot, label, tone] = HEALTH[s.health] || HEALTH.never;
  return (
    <span className={`nw-status nw-status--${tone}`} title={s.last_error || undefined}>
      <span aria-hidden="true">{dot}</span> {label}
    </span>
  );
}

export default function NewsSourcesPage() {
  const toast = useToast();
  const sources = useApi(() => newsAdminApi.sources(), [], { refreshMs: 30_000 });
  const stats = useApi(() => newsAdminApi.stats(), [], { refreshMs: 30_000 });
  const cats = useApi(() => newsAdminApi.categories(), []);
  const [busy, setBusy] = useState('');
  const [editing, setEditing] = useState(null); // null | 'new' | source
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [q, setQ] = useState('');
  const [health, setHealth] = useState('');

  const reload = () => { sources.reload(); stats.reload(); };
  const run = async (key, message, fn) => {
    setBusy(key);
    try {
      const r = await fn();
      toast.success(typeof message === 'function' ? message(r) : message);
      reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy('');
    }
  };

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (sources.data || []).filter((s) => (!term || `${s.name} ${s.url || ''} ${s.category || ''}`.toLowerCase().includes(term)) && (!health || s.health === health));
  }, [sources.data, q, health]);

  const save = async (payload) => {
    setSaving(true);
    setFormError('');
    try {
      if (editing === 'new') await newsAdminApi.createSource(payload);
      else await newsAdminApi.updateSource(editing.id, payload);
      toast.success(editing === 'new' ? 'Source added.' : 'Source updated.');
      setEditing(null);
      reload();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (sources.loading && !sources.data) return <LoadingPanel title="Loading sources…" />;
  const st = stats.data;
  const byHealth = st?.sources_by_health || {};
  const kpis = st ? [
    ['Articles', st.articles.toLocaleString()], ['Stories', st.stories.toLocaleString()], ['Multi-source stories', st.multi_source_stories],
    ['AI summaries', `${st.ai_enriched} / ${st.ai_enriched + st.ai_pending}`], ['Sources OK', `${(byHealth.active || 0)} / ${st.sources}`], ['Errors (24h)', st.errors_24h],
  ] : [];

  return (
    <div className="stack stack--lg">
      {sources.error && <Banner tone="error" title="Unable to load sources">{sources.error}</Banner>}
      <KpiGrid items={kpis} />

      <Card pad={false} className="adm-filters">
        <div className="input-wrap adm-filters__search">
          <Search size={17} aria-hidden="true" />
          <input className="input input--icon" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search sources…" aria-label="Search sources" />
        </div>
        <select className="input" value={health} onChange={(e) => setHealth(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option><option value="active">Active</option><option value="failed">Failed</option><option value="stale">Stale</option><option value="never">Not fetched</option><option value="disabled">Disabled</option>
        </select>
        <Button icon={Plus} onClick={() => { setFormError(''); setEditing('new'); }}>Add source</Button>
        <Button variant="secondary" icon={Sparkles} loading={busy === 'enrich'} onClick={() => run('enrich', (r) => (r.skipped ? 'AI enrichment is unavailable (check EVENT/NEWS AI settings).' : `AI enriched ${r.enriched} article(s)${r.failed ? `, ${r.failed} failed` : ''}.`), () => newsAdminApi.enrich(10))}>
          Run AI enrichment
        </Button>
        <Button variant="secondary" icon={Layers} loading={busy === 'recluster'} onClick={() => run('recluster', (r) => `Merged ${r.merged_groups} duplicate stories.`, () => newsAdminApi.recluster(72))}>
          Re-cluster
        </Button>
      </Card>

      <Card flush pad={false}>
        <div className="table-wrap">
          <table className="table adm-table">
            <thead>
              <tr><th>Source</th><th>Status</th><th>Last fetch</th><th>Articles</th><th>Every</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className={busy === s.id ? 'is-busy' : ''}>
                  <td>
                    <div className="adm-title">{s.name}</div>
                    <div className="text-xs muted">{s.type.toUpperCase()}{s.category ? ` · ${s.category}` : ''} · weight {s.priority}</div>
                  </td>
                  <td>
                    <Status s={s} />
                    {s.last_error && <div className="text-xs con nw-err" title={s.last_error}>{s.last_error}</div>}
                  </td>
                  <td className="nowrap">{s.last_fetch_at ? timeAgo(s.last_fetch_at) : '—'}{s.last_success_at && s.health === 'failed' ? <div className="text-xs muted">last OK {timeAgo(s.last_success_at)}</div> : null}</td>
                  <td>{s.articles_total}</td>
                  <td className="nowrap">{s.poll_minutes} min{s.consecutive_failures > 0 ? <div className="text-xs muted">backing off</div> : null}</td>
                  <td>
                    <div className="adm-actions">
                      <button type="button" className="icon-btn icon-btn--sm" title="Fetch now" aria-label={`Fetch ${s.name} now`} disabled={busy === s.id} onClick={() => run(s.id, (r) => (r.status === 'failed' ? `Fetch failed: ${r.error || 'see errors'}` : `Fetched ${s.name}: ${r.counts.created + r.counts.clustered} new, ${r.counts.unchanged} unchanged.`), () => newsAdminApi.fetchNow(s.id))}>
                        {busy === s.id ? <RefreshCw size={15} className="spin" /> : <Play size={15} />}
                      </button>
                      <button type="button" className="icon-btn icon-btn--sm" title={s.enabled ? 'Disable' : 'Enable'} aria-label={`${s.enabled ? 'Disable' : 'Enable'} ${s.name}`} aria-pressed={s.enabled} onClick={() => run(s.id, s.enabled ? `${s.name} disabled.` : `${s.name} enabled.`, () => newsAdminApi.setEnabled(s.id, !s.enabled))}>
                        <Power size={15} style={{ color: s.enabled ? 'var(--success)' : 'var(--text-faint)' }} />
                      </button>
                      <button type="button" className="icon-btn icon-btn--sm" title="Edit" aria-label={`Edit ${s.name}`} onClick={() => { setFormError(''); setEditing(s); }}><Pencil size={15} /></button>
                      <button type="button" className="icon-btn icon-btn--sm icon-btn--danger" title="Delete" aria-label={`Delete ${s.name}`} onClick={() => window.confirm(`Delete source “${s.name}”? Articles already collected are kept.`) && run(s.id, 'Source deleted.', () => newsAdminApi.deleteSource(s.id))}><Trash2 size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={6} className="muted">No sources match.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="text-sm muted">Sources are polled automatically in the background. A failing source never affects the others; it is retried with increasing delays and shown here in red.</p>

      {editing && (
        <SourceForm
          source={editing === 'new' ? null : editing}
          categories={(cats.data || []).filter((c) => !c.virtual)}
          saving={saving}
          error={formError}
          onSubmit={save}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
