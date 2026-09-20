import { Tag } from '../../ui';
import { asArray, flattenVal } from '../../../utils/data';

export default function CompetitorsPanel({ report }) {
  const competitors = asArray(report.competitors).filter((c) => {
    const n = (c?.name || '').toLowerCase();
    return n && !/^competitor\s*\d/i.test(n);
  });

  if (!competitors.length) return <p className="field-value muted">No competitor data found</p>;

  return (
    <div>
      {competitors.map((c, i) => (
        <div className="item-card" key={`${c.name}-${i}`}>
          <div className="item-card__head">
            <span className="item-card__title">{c.name}</span>
            {c.threat_level && <Tag tone="red">{flattenVal(c.threat_level)} threat</Tag>}
          </div>
          {c.description && <p className="text-sm muted" style={{ margin: '6px 0' }}>{flattenVal(c.description)}</p>}
          {c.strengths && (
            <p className="text-sm pro">
              <b>Their edge:</b> {flattenVal(c.strengths)}
            </p>
          )}
          {c.weaknesses && (
            <p className="text-sm con">
              <b>Their weakness:</b> {flattenVal(c.weaknesses)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
