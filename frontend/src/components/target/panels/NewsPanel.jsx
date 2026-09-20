import { Tag } from '../../ui';
import { asArray, flattenVal } from '../../../utils/data';

export default function NewsPanel({ report }) {
  const news = asArray(report.recent_news);
  if (!news.length) return <p className="field-value muted">No recent news found</p>;

  return (
    <div>
      {news.map((n, i) => (
        <div className="data-row" key={`${n.title}-${i}`}>
          <strong>{n.title || ''}</strong> {n.sentiment && <Tag>{flattenVal(n.sentiment)}</Tag>}
          <p className="text-sm muted" style={{ marginTop: 4 }}>
            {flattenVal(n.summary) || flattenVal(n.date)}
          </p>
        </div>
      ))}
    </div>
  );
}
