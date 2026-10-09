import { Tag } from '../../ui';
import { asArray, flattenVal } from '../../../utils/data';

const safeHttpUrl = (value) => /^https?:\/\//i.test(String(value || '').trim()) ? String(value).trim() : '';

export default function NewsPanel({ report }) {
  const news = asArray(report.recent_news).slice(0, 4);
  if (!news.length) return <p className="field-value muted">No recent, dated company news was verified in the sources checked.</p>;

  return (
    <div>
      {news.map((n, i) => {
        const sourceUrl = safeHttpUrl(n.source_url || n.url);
        const dateVerified = n.date_status === 'date-verified';
        return (
          <div className="data-row" key={`${n.title}-${i}`}>
            <strong>{n.title || 'Company update'}</strong>
            {n.sentiment && <Tag>{flattenVal(n.sentiment)}</Tag>}
            <span className={`cite-badge ${dateVerified ? 'cite-badge--high' : 'cite-badge--medium'}`}>
              {dateVerified && n.date ? flattenVal(n.date) : 'Date not verified'}
            </span>
            <p className="text-sm muted" style={{ marginTop: 4 }}>
              {flattenVal(n.summary) || 'No summary available.'}
            </p>
            {sourceUrl && (
              <a className="text-xs" href={sourceUrl} target="_blank" rel="noopener noreferrer">
                Open source
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}
