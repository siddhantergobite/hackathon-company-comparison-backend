import { IntelRow, Tag, TagList } from '../../ui';
import { asArray, hasData, isJunkText, val } from '../../../utils/data';

export default function OverviewPanel({ report }) {
  const prod = report.products_services || {};
  const mkt = report.market_analysis || {};
  const tech = report.tech_stack || {};
  const reg = report.registry_intelligence;

  const offerings = (Array.isArray(prod.primary_offerings) ? prod.primary_offerings : asArray(prod.value))
    .map((row) => (typeof row === 'string' ? { item: row } : row))
    .map((row) => ({ ...row, item: row?.item || val(row) }))
    .filter((row) => row.item && !isJunkText(row.item)
      && row.verification_status !== 'model-knowledge-reviewed');

  const mp = mkt.market_position;
  const mpText = typeof mp === 'object' ? val(mp) : mp;
  const marketPosition = !isJunkText(mpText) && hasData(mpText) ? mp : null;
  const marketTrend = mkt.market_trends;
  const marketTrendUrl = typeof marketTrend?.source_urls?.[0] === 'string'
    && /^https?:\/\//i.test(marketTrend.source_urls[0])
    ? marketTrend.source_urls[0]
    : '';

  return (
    <>
      {reg && (reg.source === 'disabled' || !reg.cin) && reg.message && (
        <div className="callout" style={{ marginBottom: 20 }}>
          <strong>Public research mode</strong>
          <p className="text-sm muted" style={{ marginTop: 6 }}>
            {reg.message}
          </p>
        </div>
      )}

      <h4 className="subhead">Products &amp; services</h4>
      {offerings.length ? (
        <TagList>
          {offerings.map((row, i) => (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }} key={`${row.item}-${i}`}>
              <Tag>{row.item}</Tag>
              {row.verification_status === 'search-snippet-supported' && (
                <span className="cite-badge cite-badge--medium">Search snippet only - page not fetched</span>
              )}
              {row.verification_status === 'evidence-verified' && (
                <span className="cite-badge cite-badge--high">Evidence checked</span>
              )}
            </span>
          ))}
        </TagList>
      ) : (
        <p className="field-value muted">—</p>
      )}
      <IntelRow label="Target customers" field={prod.target_customers} />
      <IntelRow label="Pricing model" field={prod.pricing_model} />

      <h4 className="subhead">Market position</h4>
      {marketPosition ? <IntelRow label="Market position" field={marketPosition} /> : <p className="field-value muted">—</p>}
      <IntelRow label="Industry trend context" field={marketTrend} />
      {marketTrendUrl && (
        <p className="text-xs muted" style={{ marginTop: 4 }}>
          <span className="cite-badge">
            {marketTrend?.verification_status === 'search-snippet-supported'
              ? 'Dated search result; page not fetched'
              : 'Fetched source page'}
          </span>{' '}
          <a href={marketTrendUrl} target="_blank" rel="noopener noreferrer">Open source</a>
          {marketTrend?.published_at ? ` · ${marketTrend.published_at}` : ''}
        </p>
      )}
      <IntelRow label="Geographic reach" field={mkt.geographic_reach} />

      <h4 className="subhead">Website technology</h4>
      <IntelRow label="Website CMS" field={tech.website_cms || tech.cms} />
      <p className="text-xs muted" style={{ marginTop: 8 }}>
        Detected from homepage HTML/scripts
      </p>
    </>
  );
}
