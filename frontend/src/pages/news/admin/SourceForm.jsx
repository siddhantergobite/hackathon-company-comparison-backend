import { useState } from 'react';
import { Save } from 'lucide-react';
import { Banner, Button, Modal } from '../../../components/ui';
import { Field } from '../../../components/admin/AdminBits';

const BLANK = { name: '', type: 'rss', url: '', homepage: '', category: '', poll_minutes: 15, priority: 3, enabled: true, cfg_sources: '', cfg_q: '', cfg_country: '', cfg_category: '' };

function toForm(s) {
  if (!s) return BLANK;
  const c = s.config || {};
  return {
    name: s.name || '', type: s.type || 'rss', url: s.url || '', homepage: s.homepage || '', category: s.category || '',
    poll_minutes: s.poll_minutes ?? 15, priority: s.priority ?? 3, enabled: s.enabled !== false,
    cfg_sources: c.sources || '', cfg_q: c.q || '', cfg_country: c.country || '', cfg_category: c.category || '',
  };
}

function toPayload(f, editing) {
  const body = {
    url: f.type === 'rss' ? f.url.trim() : null,
    homepage: f.homepage.trim() || null,
    category: f.category || null,
    poll_minutes: Number(f.poll_minutes),
    priority: Number(f.priority),
  };
  if (f.type === 'newsapi') {
    body.config = Object.fromEntries(Object.entries({ mode: 'top-headlines', sources: f.cfg_sources.trim(), q: f.cfg_q.trim(), country: f.cfg_country.trim(), category: f.cfg_category.trim() }).filter(([, v]) => v));
  }
  if (!editing) Object.assign(body, { name: f.name.trim(), type: f.type, enabled: f.enabled });
  else body.name = f.name.trim();
  return body;
}

export default function SourceForm({ source, categories, saving, error, onSubmit, onClose }) {
  const editing = Boolean(source);
  const [f, setF] = useState(() => toForm(source));
  const [local, setLocal] = useState('');
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    if (f.name.trim().length < 2) return setLocal('Enter a name.');
    if (f.type === 'rss' && !/^https?:\/\//i.test(f.url.trim())) return setLocal('Enter the feed URL (starting with http:// or https://).');
    if (f.type === 'newsapi' && !(f.cfg_sources || f.cfg_q || f.cfg_country || f.cfg_category)) return setLocal('NewsAPI needs at least one of: sources, search query, country or category.');
    setLocal('');
    return onSubmit(toPayload(f, editing));
  };

  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={editing ? `Edit “${source.name}”` : 'Add news source'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="source-form" icon={Save} loading={saving}>{editing ? 'Save changes' : 'Add source'}</Button>
        </>
      }
    >
      <form id="source-form" onSubmit={submit} className="stack" noValidate>
        {(local || error) && <Banner tone="error">{local || error}</Banner>}
        <div className="adm-grid">
          <Field label="Name" htmlFor="s-name" required>
            <input id="s-name" className="input" value={f.name} onChange={set('name')} placeholder="e.g. The Economist" />
          </Field>
          <Field label="Type" htmlFor="s-type" hint={f.type === 'newsapi' ? 'Needs NEWS_API_KEY on the server.' : 'RSS or Atom feed.'}>
            <select id="s-type" className="input" value={f.type} onChange={set('type')} disabled={editing}>
              <option value="rss">RSS / Atom feed</option>
              <option value="newsapi">NewsAPI (Reuters, AP, …)</option>
            </select>
          </Field>
          {f.type === 'rss' && (
            <Field label="Feed URL" htmlFor="s-url" required wide hint="Public feed the publisher offers for readers. Private/internal addresses are refused.">
              <input id="s-url" className="input" type="url" value={f.url} onChange={set('url')} placeholder="https://example.com/feed.xml" />
            </Field>
          )}
          {f.type === 'newsapi' && (
            <>
              <Field label="NewsAPI sources" htmlFor="s-cs" hint="Comma-separated ids, e.g. reuters,associated-press"><input id="s-cs" className="input" value={f.cfg_sources} onChange={set('cfg_sources')} /></Field>
              <Field label="Search query" htmlFor="s-cq"><input id="s-cq" className="input" value={f.cfg_q} onChange={set('cfg_q')} /></Field>
              <Field label="Country (2-letter)" htmlFor="s-cc"><input id="s-cc" className="input" maxLength={2} value={f.cfg_country} onChange={set('cfg_country')} placeholder="in" /></Field>
              <Field label="NewsAPI category" htmlFor="s-ccat"><input id="s-ccat" className="input" value={f.cfg_category} onChange={set('cfg_category')} placeholder="technology" /></Field>
            </>
          )}
          <Field label="Website" htmlFor="s-home"><input id="s-home" className="input" type="url" value={f.homepage} onChange={set('homepage')} placeholder="https://example.com" /></Field>
          <Field label="Default category" htmlFor="s-cat" hint="A hint used when the article text doesn't decide.">
            <select id="s-cat" className="input" value={f.category} onChange={set('category')}>
              <option value="">Detect automatically</option>
              {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Poll every (minutes)" htmlFor="s-poll" hint="Failing sources back off automatically.">
            <input id="s-poll" className="input" type="number" min={1} max={1440} value={f.poll_minutes} onChange={set('poll_minutes')} />
          </Field>
          <Field label="Editorial weight (1–5)" htmlFor="s-pri" hint="Higher = counts more toward importance & lead article.">
            <input id="s-pri" className="input" type="number" min={1} max={5} value={f.priority} onChange={set('priority')} />
          </Field>
          {!editing && (
            <label className="adm-check" style={{ alignSelf: 'end', paddingBottom: 10 }}>
              <input type="checkbox" checked={f.enabled} onChange={set('enabled')} /> Enabled (start polling right away)
            </label>
          )}
        </div>
      </form>
    </Modal>
  );
}
