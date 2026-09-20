import { Tag, TagList } from '../ui';
import { asArray, ensureUrl, flattenVal } from '../../utils/data';

const none = (text) => <p className="field-value muted">{text}</p>;

export function TopicsSection({ data }) {
  const topics = asArray(data.topic_research);
  if (!topics.length) return none('No topic results');
  return (
    <div>
      {topics.map((t, i) => (
        <div className="item-card" key={`${t.topic}-${i}`}>
          <div className="item-card__title">{flattenVal(t.topic)}</div>
          <div style={{ margin: '10px 0' }}>
            <div className="field-label">Winning domains</div>
            {asArray(t.winner_domains).length ? (
              <TagList>
                {t.winner_domains.map((d) => (
                  <Tag tone="amber" key={d}>
                    {d}
                  </Tag>
                ))}
              </TagList>
            ) : (
              <span className="muted">—</span>
            )}
          </div>
          {asArray(t.top_results)
            .slice(0, 3)
            .map((r, j) => (
              <div className="data-row" key={`${r.url}-${j}`}>
                <a href={ensureUrl(r.url)} target="_blank" rel="noopener noreferrer">
                  {r.title || r.url}
                </a>
              </div>
            ))}
        </div>
      ))}
    </div>
  );
}

const SEVERITY_TONE = { high: 'red', critical: 'red', medium: 'amber', med: 'amber', low: 'teal' };

export function GapsSection({ data }) {
  const gaps = asArray(data.analysis?.gaps);
  if (!gaps.length) return none('No gaps listed');
  return (
    <div>
      {gaps.map((g, i) => (
        <div className="item-card" key={i}>
          <div className="row" style={{ gap: 8 }}>
            {g.severity && <Tag tone={SEVERITY_TONE[String(g.severity).toLowerCase()] || 'red'}>{g.severity}</Tag>}
            {g.area && <Tag tone="neutral">{g.area}</Tag>}
          </div>
          <p style={{ marginTop: 10, fontWeight: 600 }}>{g.finding}</p>
          {g.why_it_matters && <p className="text-sm muted" style={{ marginTop: 4 }}>{g.why_it_matters}</p>}
        </div>
      ))}
    </div>
  );
}

export function RecommendationsSection({ data }) {
  const recs = asArray(data.analysis?.recommendations);
  if (!recs.length) return none('No recommendations');
  return (
    <div>
      {recs.map((rec, i) => (
        <div className="rec-card" key={i}>
          <div className="row" style={{ gap: 8 }}>
            {rec.priority && <Tag tone="red">{rec.priority}</Tag>}
            {rec.type && <Tag tone="neutral">{rec.type}</Tag>}
            {rec.page && <Tag tone="amber">{rec.page}</Tag>}
          </div>
          <div className="rec-card__title">{rec.title}</div>
          {rec.why && <p className="text-sm muted" style={{ marginTop: 4 }}>{rec.why}</p>}
          <div className="diff">
            <div>
              <span className="diff__label diff__label--before">Before</span>
              <pre className="code-block">{rec.before || '—'}</pre>
            </div>
            <div>
              <span className="diff__label diff__label--after">After</span>
              <pre className="code-block">{rec.after || '—'}</pre>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function FaqsSection({ data }) {
  const faqs = asArray(data.analysis?.suggested_faqs);
  if (!faqs.length) return none('No FAQs suggested');
  return (
    <div>
      {faqs.map((f, i) => (
        <div className="faq" key={i}>
          <div className="faq__q">Q: {f.question}</div>
          <div className="faq__a">A: {f.answer}</div>
        </div>
      ))}
    </div>
  );
}

export function GeoSection({ data }) {
  const geo = data.geo_snapshot || {};
  const mentions = asArray(geo.external_mentions).slice(0, 8);
  const kinds = asArray(geo.mention_kinds);
  return (
    <>
      {geo.note && <p className="field-value" style={{ marginBottom: 12 }}>{geo.note}</p>}
      {kinds.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <TagList>
            {kinds.map((k) => (
              <Tag tone="amber" key={k}>
                {k}
              </Tag>
            ))}
          </TagList>
        </div>
      )}
      {mentions.length ? (
        mentions.map((m, i) => (
          <div className="data-row" key={`${m.url}-${i}`}>
            <Tag tone="neutral">{m.kind || 'other'}</Tag>{' '}
            <a href={ensureUrl(m.url)} target="_blank" rel="noopener noreferrer">
              {m.title || m.url}
            </a>
          </div>
        ))
      ) : (
        none('No external mentions found yet')
      )}
    </>
  );
}

export function ChecklistSection({ data }) {
  const items = asArray(data.analysis?.distribution_checklist);
  if (!items.length) return none('—');
  return (
    <div>
      {items.map((c, i) => (
        <div className="data-row" key={i}>
          {c.helps && <Tag tone="neutral">{c.helps}</Tag>} <strong>{c.action}</strong>
          {c.done_hint && <span className="muted"> — {c.done_hint}</span>}
        </div>
      ))}
    </div>
  );
}
