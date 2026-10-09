import { CiteBadge } from '../../ui';
import { asArray, hasData, pointOf } from '../../../utils/data';

function SwotBox({ tone, title, items }) {
  const rows = asArray(items)
    .map((item) => ({ item, text: pointOf(item) }))
    .filter(({ text }) => hasData(text));
  return (
    <div className={`swot-box swot-box--${tone}`}>
      <h5>{title}</h5>
      <ul>
        {rows.length ? (
          rows.map(({ item, text }, i) => (
            <li key={`${text}-${i}`}>
              {text}
              {typeof item === 'object' && <CiteBadge field={item} />}
              {typeof item === 'object' && item.basis === 'analysis' && (
                <span className="cite-badge cite-badge--medium">Analysis based on cited evidence</span>
              )}
              {typeof item === 'object' && /^https?:\/\//i.test(String(item.source_url || '')) && (
                <a className="text-xs" href={item.source_url} target="_blank" rel="noopener noreferrer">Source</a>
              )}
            </li>
          ))
        ) : (
          <li>No company-specific public evidence supported this category.</li>
        )}
      </ul>
    </div>
  );
}

export default function SwotPanel({ report }) {
  const swot = report.swot_analysis || {};
  return (
    <div className="swot-grid">
      <SwotBox tone="s" title="Strengths" items={swot.strengths} />
      <SwotBox tone="w" title="Weaknesses" items={swot.weaknesses} />
      <SwotBox tone="o" title="Opportunities" items={swot.opportunities} />
      <SwotBox tone="t" title="Threats" items={swot.threats} />
    </div>
  );
}
