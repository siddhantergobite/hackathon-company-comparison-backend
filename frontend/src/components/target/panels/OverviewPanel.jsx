import { IntelRow, Tag, TagList } from '../../ui';
import { asArray, hasData, isJunkText, pointOf, val } from '../../../utils/data';

export default function OverviewPanel({ report }) {
  const prod = report.products_services || {};
  const mkt = report.market_analysis || {};
  const tech = report.tech_stack || {};
  const reg = report.registry_intelligence;

  const offerings = (Array.isArray(prod.primary_offerings) ? prod.primary_offerings : asArray(prod.value))
    .map(pointOf)
    .filter((name) => name && !isJunkText(name));

  const mp = mkt.market_position;
  const mpText = typeof mp === 'object' ? val(mp) : mp;
  const marketPosition = !isJunkText(mpText) && hasData(mpText) ? mp : null;

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
          {offerings.map((name, i) => (
            <Tag key={`${name}-${i}`}>{name}</Tag>
          ))}
        </TagList>
      ) : (
        <p className="field-value muted">—</p>
      )}
      <IntelRow label="Target customers" field={prod.target_customers} />
      <IntelRow label="Pricing model" field={prod.pricing_model} />

      <h4 className="subhead">Market position</h4>
      {marketPosition ? <IntelRow label="Market position" field={marketPosition} /> : <p className="field-value muted">—</p>}
      <IntelRow label="Geographic reach" field={mkt.geographic_reach} />

      <h4 className="subhead">Website technology</h4>
      <IntelRow label="Website CMS" field={tech.website_cms || tech.cms} />
      <p className="text-xs muted" style={{ marginTop: 8 }}>
        Detected from homepage HTML/scripts
      </p>
    </>
  );
}
