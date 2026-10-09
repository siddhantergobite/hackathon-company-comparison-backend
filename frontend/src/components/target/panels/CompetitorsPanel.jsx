import { Tag } from '../../ui';
import { asArray, flattenVal } from '../../../utils/data';

const safeHttpUrl = (value) => /^https?:\/\//i.test(String(value || '').trim()) ? String(value).trim() : '';

export default function CompetitorsPanel({ report }) {
  const competitors = asArray(report.competitors).filter((c) => {
    const n = (c?.name || '').toLowerCase();
    return n && !/^competitor\s*\d/i.test(n);
  });
  const suggestions = asArray(report.competitor_candidates).filter((c) => c?.name);

  return (
    <div>
      {competitors.length ? (
        competitors.map((c, i) => {
          const sourceUrl = safeHttpUrl(c.evidence_url || c.source_url);
          return (
            <div className="item-card" key={`${c.name}-${i}`}>
              <div className="item-card__head">
                <span className="item-card__title">{c.name}</span>
                {c.threat_level && <Tag tone="red">{flattenVal(c.threat_level)} threat</Tag>}
              </div>
              {c.official_domain && <p className="text-xs muted">{c.official_domain}</p>}
              {c.market_location && <p className="text-xs muted">Market: {flattenVal(c.market_location)}</p>}
              {(c.overlap_reason || c.description) && (
                <p className="text-sm muted" style={{ margin: '6px 0' }}>
                  {flattenVal(c.overlap_reason || c.description)}
                </p>
              )}
              {c.strengths && <p className="text-sm pro"><b>Their edge:</b> {flattenVal(c.strengths)}</p>}
              {c.weaknesses && <p className="text-sm con"><b>Their weakness:</b> {flattenVal(c.weaknesses)}</p>}
              {sourceUrl && (
                <a className="text-xs" href={sourceUrl} target="_blank" rel="noopener noreferrer">
                  Evidence source
                </a>
              )}
            </div>
          );
        })
      ) : (
        <p className="field-value muted">No direct competitors were confirmed by the retrieved public evidence.</p>
      )}

      {suggestions.length > 0 && (
        <div className="callout" style={{ marginTop: 16 }}>
          <strong>AI suggested competitors - unverified</strong>
          <p className="text-sm muted" style={{ marginTop: 6 }}>
            These are research leads based on model knowledge. Treat them as candidates until their market overlap is checked against current sources.
          </p>
          {suggestions.slice(0, 4).map((c, i) => {
            const sourceUrl = safeHttpUrl(asArray(c.source_urls)[0]);
            return (
              <div className="data-row" key={`${c.name}-${i}`}>
                <strong>{c.name}</strong>
                {c.official_domain && <span className="cite-badge">{c.official_domain}</span>}
                {c.market_location && <span className="cite-badge">{flattenVal(c.market_location)}</span>}
                {c.overlap_reason && <p className="text-sm muted">{flattenVal(c.overlap_reason)}</p>}
                {sourceUrl && (
                  <a className="text-xs" href={sourceUrl} target="_blank" rel="noopener noreferrer">
                    Candidate reference
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
