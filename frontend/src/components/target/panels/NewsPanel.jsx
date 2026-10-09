import { Tag } from '../../ui';
import { asArray, flattenVal } from '../../../utils/data';

const safeHttpUrl = (value) => /^https?:\/\//i.test(String(value || '').trim()) ? String(value).trim() : '';

export default function NewsPanel({ report }) {
  const news = asArray(report.recent_news).slice(0, 4);
  if (!news.length) return <p className="field-value muted">No company news or events with a verifiable date were found in the accessible public sources checked.</p>;

  return (
    <div>
      {news.map((n, i) => {
        const sourceUrl = safeHttpUrl(n.source_url || n.url);
        const dateVerified = String(n.date_status || '').startsWith('date-verified');
        const upcoming = n.date_status === 'date-verified-upcoming';
        const kind = String(n.kind || '').toLowerCase() === 'event' ? 'Event' : 'News';
        return (
          <div className="data-row" key={`${n.title}-${i}`}>
            <strong>{n.title || 'Company update'}</strong>
            <Tag>{kind}</Tag>
            <span className={`cite-badge ${dateVerified ? 'cite-badge--high' : 'cite-badge--medium'}`}>
              {dateVerified && n.date ? `${upcoming ? 'Upcoming · ' : ''}${flattenVal(n.date)}` : 'Date not verified'}
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
