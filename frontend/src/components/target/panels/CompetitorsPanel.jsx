import { Tag } from '../../ui';
import { asArray, flattenVal } from '../../../utils/data';

const safeHttpUrl = (value) => /^https?:\/\//i.test(String(value || '').trim()) ? String(value).trim() : '';
const hostFromUrl = (value) => {
  const url = safeHttpUrl(value);
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./i, '');
  } catch {
    return '';
  }
};

export default function CompetitorsPanel({ report }) {
  const competitors = asArray(report.competitors).filter((c) => {
    const n = (c?.name || '').toLowerCase();
    return n && !/^competitor\s*\d/i.test(n);
  });
  const directNames = new Set(competitors.map((c) => String(c.name || '').trim().toLowerCase()));
  const sourcedReferences = asArray(report.competitor_candidates).filter((c) => {
    const name = String(c?.name || '').trim().toLowerCase();
    const supported = ['evidence-verified', 'search-snippet-supported'].includes(c?.verification_status);
    return name && !directNames.has(name) && supported
      && asArray(c.source_urls).some((url) => safeHttpUrl(url));
  });

  return (
    <div>
      {competitors.length ? (
        competitors.map((c, i) => {
          const sourceUrl = safeHttpUrl(c.evidence_url || c.source_url);
          const sourceHost = hostFromUrl(sourceUrl);
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
                  Source: {sourceHost || 'open evidence'}
                </a>
              )}
            </div>
          );
        })
      ) : (
        <p className="field-value muted">No direct competitors were confirmed from fetched public pages.</p>
      )}

      {sourcedReferences.length > 0 && (
        <section style={{ marginTop: 18 }}>
          <h4 className="subhead">Competitor leads from public sources</h4>
          {sourcedReferences.slice(0, 4).map((c, i) => {
            const sourceUrls = asArray(c.source_urls).map(safeHttpUrl).filter(Boolean).slice(0, 3);
            return (
              <div className="data-row" key={`${c.name}-${i}`}>
                <strong>{c.name}</strong>
                <span className="cite-badge">
                  {c.verification_status === 'evidence-verified' ? 'Page checked' : 'Search result'}
                </span>
                {c.official_domain && <span className="cite-badge">{c.official_domain}</span>}
                {c.market_location && <span className="cite-badge">{flattenVal(c.market_location)}</span>}
                {c.overlap_reason && (
                  <p className="text-sm muted">Potential overlap: {flattenVal(c.overlap_reason)}</p>
                )}
                <div className="text-xs muted">
                  Sources:{' '}
                  {sourceUrls.map((url, sourceIndex) => (
                    <span key={url}>
                      {sourceIndex > 0 ? ' · ' : ''}
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        {hostFromUrl(url) || 'open source'}
                      </a>
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
